# app/services/rolling_ols.py
import os
import json
import logging
import datetime
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
import statsmodels.api as sm
import joblib
from app.core.config import settings
from app.utils import get_experiment_dir, safe_to_csv, get_root_data_dir, save_json, get_relative_path
from app.schemas.enums import DataPathType, ExperimentStatus
from app.services.train_test_split import DEFAULT_FACTOR_COLS, DEFAULT_Y_COL
from app.utils.exceptions import BusinessError
from app.database.experiment_repo import experiment_repo

logger = logging.getLogger(__name__)


def run_rolling_ols(
    window: int = 252,
    zscore_window: int = 52,
    buy_threshold: float = 0.5,
    sell_threshold: float = -0.5,
    factor_cols: list = None,
    y_col: str = None,
    exp_id: int = None,
    force_full_train: bool = False
) -> dict:
    """
    执行滚动 OLS 训练，生成预测信号并保存结果。

    - window: 滚动窗口大小
    - zscore_window: zscore信号窗口,默认按52周即1年滚动
    - buy_threshold: 买入信号阈值,参考0.3 ~ 1.5
    - sell_threshold: 卖出信号阈值,参考-1.5 ~ -0.3
    - factor_cols: 因子列表
    - y_col: 自变量
    - exp_id: 实验编号(必填)
    - force_full_train: 强制全量训练

    返回:
        dict 包含训练信息（样本数、信号分布等）
    """
    # 校验和设置初值
    if exp_id is None:
        raise BusinessError(f"实验ID不可为空")
    
    experiment = experiment_repo.get(exp_id=exp_id)
    if experiment is None:
        raise BusinessError(f"实验记录不存在")
    
    # 默认路径    
    if factor_cols is None:
        factor_cols = DEFAULT_FACTOR_COLS
    if y_col is None:
        y_col = DEFAULT_Y_COL
    
    # 读取分割后的数据目录
    split_rel = experiment.get('split_dir')
    status : ExperimentStatus = experiment.get('status')
    if not split_rel and status !=  ExperimentStatus.SPLITTED:
        raise BusinessError("该实验尚未完成数据分割")
    split_dir = get_root_data_dir() / split_rel
    
    train_csv = split_dir / "train.csv"
    test_csv = split_dir / "test.csv"

    # ---------- 前置检查：确保训练/测试数据存在 ----------
    missing = []
    if not os.path.exists(train_csv):
        missing.append(train_csv)
    if not os.path.exists(test_csv):
        missing.append(test_csv)
    if missing:
        raise BusinessError(
            f"缺少数据文件，请先执行训练/测试集划分：{', '.join(missing)}"
        )

    # ---------- 判断是否为增量训练 ----------
    locked_date = experiment.get('split_cutoff_date')
    model_dir_rel = experiment.get('train_model_dir')
    exp_dir = get_experiment_dir(exp_id, experiment["experiment_name"], DataPathType.model)
    predictions_csv = exp_dir / "predictions.csv"

    # 判断是否执行增量训练
    is_incremental = (
        not force_full_train            # 强制全量训练
        and locked_date                 # 分割训练集日期
        and model_dir_rel               # 此前的模型保存地址
        and predictions_csv.exists()    # 存在旧的预测集
    )

    
    if is_incremental:
        logger.info("实验 #%d 检测到增量训练条件，执行增量训练", exp_id)
        return _incremental_train(
            experiment, exp_dir, split_dir,
            window, zscore_window, buy_threshold, sell_threshold,
            factor_cols, y_col, predictions_csv, model_dir_rel
        )
    else:
        logger.info("实验 #%d 执行全量训练", exp_id)
        return _full_train(
            experiment, exp_dir, split_dir,
            window, zscore_window, buy_threshold, sell_threshold,
            factor_cols, y_col
        )

def _full_train(
    experiment, exp_dir, split_dir,
    window, zscore_window, buy_threshold, sell_threshold,
    factor_cols, y_col
):
    """全量滚动训练，覆盖或创建 predictions.csv，并保存最终模型状态"""
    
    # ---------- 开始训练 ----------
    # 加载数据
    train_csv = split_dir / "train.csv"
    test_csv = split_dir / "test.csv"
    train = pd.read_csv(train_csv, parse_dates=['date'])
    test = pd.read_csv(test_csv, parse_dates=['date'])

    # 提取因子列（lag1 版本）和标签
    X_train = train[[f'{c}_lag1' for c in factor_cols]]
    y_train = train[y_col]
    X_test = test[[f'{c}_lag1' for c in factor_cols]]
    y_test = test[y_col]

    # 滚动训练
    predictions = []
    window_eff = min(window, len(X_train) + len(X_test))  # 防止窗口过大
    for i in range(len(X_test)):
        if i == 0:
            # 第一个测试周，只用 X_train 和 y_train
            X_roll = X_train.values
            y_roll = y_train.values
        else:
            # 扩展窗口：X_train + 已经过的测试周（不含本周）
            # np.vstack 和 np.hstack 分别是 numpy 中的垂直堆叠和水平堆叠函数。
            # 用来把最初的训练集（X_train / y_train）和已经预测过的测试周（前 i 周）合并在一起，
            # 构成一个时间上连续的、截止到上周为止的全量历史数据
            # 此处堆叠用于将测试集中已经过去的周得到的新数据堆叠到训练集中，用于训练对于的新模型
            X_roll = np.vstack([X_train.values, X_test.iloc[:i].values])
            y_roll = np.hstack([y_train.values, y_test.iloc[:i].values])

        # 取最近 window 条样本
        if len(X_roll) > window_eff:
            X_roll = X_roll[-window_eff:]
            y_roll = y_roll[-window_eff:]

        # ---------- 标准化 ----------
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_roll)
        # 手动添加截距列（全1列）
        X_with_const = np.column_stack([np.ones(len(X_scaled)), X_scaled])

        model = sm.OLS(y_roll, X_with_const).fit()

        # ---------- 预测当前周 ----------
        # 取当前周的因子值（1行）
        # X_test.iloc[i].values得到一维数组，形状为(特征数,)
        # reshape(1,-1)用于将一维数组转换为二维数组，形状为(1,特征数)
        # 例如array([0.003, 101.8, 4.0])转为array([[0.003, 101.8, 4.0]])
        # 1表示新的行数为1，-1表示自动计算列数
        X_now = X_test.iloc[i].values.reshape(1, -1)
        X_now_scaled = scaler.transform(X_now)
        # np.column_stack将多个一维或二维数组按列拼接。
        # np.ones(1) 生成一个长度为 1 的全 1 数组（形状 (1,)）。
        # 拼接后，X_now_const 变成 (1, 特征数+1)，第一列全是 1，后面是标准化后的特征。
        X_now_const = np.column_stack([np.ones(1), X_now_scaled])

        pred = model.predict(X_now_const)[0]
        predictions.append(pred)

    test['predicted_return'] = predictions

    # Z-Score 信号（基于过去zscore_window周约1年预测值的分布）
    # 公式：Z = (X - μ) / σ
    # 表示当前预测值与过去一年预测值的平均水平相比，处于多少个标准差的位置。正值表示高于平均水平，负值表示低于平均水平，绝对值越大表示偏离程度越显著。
    test['pred_zscore'] = (
        test['predicted_return'] - test['predicted_return'].rolling(zscore_window, min_periods=10).mean()
    ) / test['predicted_return'].rolling(zscore_window, min_periods=10).std()

    # 信号映射（需要趋势列，如果 test 中没有 trend，则从周频数据补充）
    if 'trend' not in test.columns:
        logger.warning("测试集缺少趋势列trend参数，请确认分割数据集运算是否正确")
        raise BusinessError(
            f"测试集缺少趋势列trend参数，请确认分割数据集运算是否正确"
        )

    def generate_signal(row):
        #  weekly['trend'] = (weekly['nav'] > weekly['ma26']).astype(int)  # 1:多头, 0:空头
        # trend = 0 表示空头，即当前金价处于26周均线下方，趋势较弱，不建议操作，保持观望
        if row.get('trend', 1) == 0:
            return 0
        z = row['pred_zscore']
        if z > buy_threshold: # 预测值显著高于过去一年平均水平，且当前处于多头趋势，给出买入信号
            return 1
        elif z < sell_threshold: # 预测值显著低于过去一年平均水平，且当前处于多头趋势，给出卖出信号
            return -1
        return 0 # 预测值接近过去一年平均水平，且当前处于多头趋势，保持观望阿


    test['signal'] = test.apply(generate_signal, axis=1)


    # ========== 保存输出到实验专属目录 ==========
    # 保存预测结果
    pred_cols = ['date', 'trend', 'predicted_return', 'pred_zscore', 'signal', 'nav', 'nav_return']
    safe_to_csv(test[pred_cols], exp_dir/"predictions.csv")

    # 保存最新一周信号
    latest = test.iloc[-1:]
    safe_to_csv(latest[pred_cols], exp_dir/"latest_signal.csv")

    # # 保存最后一期模型系数和标准化器（用于实盘预测）
    # coef_dict = dict(zip(['const'] + [f'{c}_lag1' for c in factor_cols], model.params))
    # save_json(coef_dict, exp_dir / "ols_coefficients.json")
    # joblib.dump(scaler, exp_dir / "scaler.joblib")

    # 保存完整窗口模型（用于增量训练）
    last_model = {
        'coef': dict(zip(['const'] + [f'{c}_lag1' for c in factor_cols], model.params)),
        'scaler': scaler,
        'window': window_eff,
    }
    model_path = exp_dir / "last_window_model.joblib"
    joblib.dump(last_model, model_path)


    # ========== 更新数据库实验记录 ==========
    experiment_repo.update(experiment['id'],
        status=ExperimentStatus.TRAINED,
        train_dir=get_relative_path(exp_dir),
        train_model_dir=get_relative_path(model_path),   # 新增字段
        train_ols_window=window_eff,
        train_zscore_window=zscore_window,
        train_buy_threshold=buy_threshold,
        train_sell_threshold=sell_threshold,
        train_ols_train_samples=len(X_train),
        train_ols_test_samples=len(X_test)
    )

    logger.info("滚动训练完成，信号已保存至 %s", exp_dir)


    ret = experiment_repo.get(experiment['id'])
     # 返回关键信息
    return ret


def _incremental_train(
    experiment, exp_dir, split_dir,
    window, zscore_window, buy_threshold, sell_threshold,
    factor_cols, y_col, predictions_csv, model_dir_rel
):
    """增量训练：加载历史预测，对新数据追加预测信号"""
    # 读取历史预测
    hist_pred = pd.read_csv(predictions_csv, parse_dates=['date'])
    last_pred_date = hist_pred['date'].max()

    # 读取最新测试集（已包含所有新旧数据）
    test_csv = split_dir / "test.csv"
    test_full = pd.read_csv(test_csv, parse_dates=['date'])

    # 筛选新增数据（日期 > 最后预测日期）
    new_test = test_full[test_full['date'] > last_pred_date].copy()
    if len(new_test) == 0:
        logger.info("无新增数据，跳过增量训练")
        return experiment_repo.get(experiment['id'])

    # 加载历史模型
    model_path = get_root_data_dir() / model_dir_rel
    if not model_path.exists():
        raise BusinessError(f"增量模型文件不存在: {model_path}")
    last_model = joblib.load(model_path)
    # scaler 和 coef 仅作参考，增量训练时会重新拟合

    # 构建历史数据窗口：train.csv + 测试集中已预测过的部分
    train_csv = split_dir / "train.csv"
    train = pd.read_csv(train_csv, parse_dates=['date'])
    hist_test = test_full[test_full['date'] <= last_pred_date].copy()
    hist_all = pd.concat([train, hist_test]).sort_values('date')        # 训练集=旧训练集+已经预测过的测试集

    factor_lag_cols = [f'{c}_lag1' for c in factor_cols]
    X_hist = hist_all[factor_lag_cols].values   # 只保留训练用列数据
    y_hist = hist_all[y_col].values

    new_predictions = []
    window_eff = min(window, len(X_hist) + len(new_test))

    for i in range(len(new_test)):
        if i == 0:
            X_roll = X_hist
            y_roll = y_hist
        else:
            X_roll = np.vstack([X_hist, new_test.iloc[:i][factor_lag_cols].values])
            y_roll = np.hstack([y_hist, new_test.iloc[:i][y_col].values])

        if len(X_roll) > window_eff:
            X_roll = X_roll[-window_eff:]
            y_roll = y_roll[-window_eff:]

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_roll)
        X_with_const = np.column_stack([np.ones(len(X_scaled)), X_scaled])
        model = sm.OLS(y_roll, X_with_const).fit()

        X_now = new_test.iloc[i][factor_lag_cols].values.reshape(1, -1)
        X_now_scaled = scaler.transform(X_now)
        X_now_const = np.column_stack([np.ones(1), X_now_scaled])
        pred = model.predict(X_now_const)[0]
        new_predictions.append(pred)

    # 构建新增预测 DataFrame
    new_pred_df = new_test[['date', 'trend', 'nav', 'nav_return']].copy()
    new_pred_df['predicted_return'] = new_predictions

    # 计算 pred_zscore（需要包含历史预测的完整序列）
    all_pred = pd.concat([hist_pred[['date', 'predicted_return']], new_pred_df[['date', 'predicted_return']]]).sort_values('date')
    all_pred['pred_zscore'] = (
        all_pred['predicted_return'] - all_pred['predicted_return'].rolling(zscore_window, min_periods=10).mean()
    ) / all_pred['predicted_return'].rolling(zscore_window, min_periods=10).std()
    # 只取新增部分
    new_pred_df['pred_zscore'] = all_pred.iloc[len(hist_pred):]['pred_zscore'].values

    if 'trend' not in new_pred_df.columns:
        raise BusinessError("新增数据缺少趋势列trend")

    def generate_signal(row):
        if row.get('trend', 1) == 0:
            return 0
        z = row['pred_zscore']
        if z > buy_threshold:
            return 1
        elif z < sell_threshold:
            return -1
        return 0

    new_pred_df['signal'] = new_pred_df.apply(generate_signal, axis=1) # axis=1 表示 将函数 generate_signal 应用于 DataFrame 的每一行

    # 合并历史与新增预测
    updated_pred = pd.concat([hist_pred, new_pred_df[['date', 'trend', 'predicted_return', 'pred_zscore', 'signal', 'nav', 'nav_return']]])
    safe_to_csv(updated_pred, predictions_csv)
    safe_to_csv(new_pred_df.iloc[-1:][['date', 'trend', 'predicted_return', 'pred_zscore', 'signal', 'nav', 'nav_return']], exp_dir / "latest_signal.csv")

    # 更新模型文件（保存最新的窗口状态）
    last_model_new = {
        'coef': dict(zip(['const'] + factor_lag_cols, model.params)),
        'scaler': scaler,
        'window': window_eff,
    }
    new_model_path = exp_dir / "last_window_model.joblib"
    joblib.dump(last_model_new, new_model_path)

    # 更新数据库
    experiment_repo.update(experiment['id'],
        status=ExperimentStatus.TRAINED,
        train_dir=get_relative_path(exp_dir),
        train_model_dir=get_relative_path(new_model_path),
        train_ols_window=window_eff,
        train_zscore_window=zscore_window,
        train_buy_threshold=buy_threshold,
        train_sell_threshold=sell_threshold,
        train_ols_train_samples=len(train),
        train_ols_test_samples=len(test_full)
    )
    logger.info("增量训练完成，新增 %d 周信号", len(new_test))
    return experiment_repo.get(experiment['id'])