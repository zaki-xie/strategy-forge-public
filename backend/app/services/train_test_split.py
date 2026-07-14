# app/services/train_test_split.py
import os
import json
import logging
import datetime
import pandas as pd
from app.core.config import settings
from app.utils import get_experiment_dir, get_root_data_dir, safe_to_csv, get_relative_path
from app.schemas.enums import DataPathType, ExperimentStatus
from app.utils.exceptions import BusinessError
from app.database.experiment_repo import experiment_repo

logger = logging.getLogger(__name__)

# 默认因子列和标签列（与策略保持一致）
DEFAULT_FACTOR_COLS = [
    'au_return',        # 国内金价周收益率
    'gold_int_return',  # 国际金价周收益率
    'dxy',              # 美元指数
    'us10y',            # 美债利率
    'brent',            # 原油价格
    'spdr_change',      # SPDR持仓周变化
    'deviation'         # 价格与均线偏离度
]
DEFAULT_Y_COL = 'nav_return'


def split_train_test(
    split_ratio: float = 0.7,
    factor_cols: list[str] = None,
    y_col: str = None,
    exp_id: int = None
) -> dict:
    """
    从周频数据中划分训练集和测试集，构建滞后一期的因子矩阵。

    参数:
        split_ratio: 训练集占比，默认 0.7
        factor_cols: 因子列名列表，默认 DEFAULT_FACTOR_COLS
        y_col: 标签列名，默认 'nav_return'
        exp_id: 实验ID
    返回:
        dict 包含训练/测试集划分信息
    """
    # 校验
    if exp_id is None:
        raise BusinessError(f"实验ID不可为空")
    
    experiment = experiment_repo.get(exp_id=exp_id)
    if not experiment:
        raise BusinessError(f"实验记录不存在")

    # 周频数据路径
    weekly_rel = experiment.get('weekly_dir')
    status : ExperimentStatus = experiment.get('status')
    if not weekly_rel and status != ExperimentStatus.WEEKLY_AGGREGATOR:
        raise BusinessError("该实验尚未完成周频聚合")
    weekly_csv_path = get_root_data_dir() / weekly_rel / "weekly_data.csv"
    
    if factor_cols is None:
        factor_cols = DEFAULT_FACTOR_COLS
    if y_col is None:
        y_col = DEFAULT_Y_COL

    # 加载周频数据
    logger.info("加载周频数据: %s", weekly_csv_path)
    weekly_df = pd.read_csv(weekly_csv_path, parse_dates=['date']).sort_values('date')
    logger.info("周频数据行数: %d", len(weekly_df))
    
    for col in factor_cols:
        weekly_df[f'{col}_lag1'] = weekly_df[col].shift(1)

    # --- 诊断：打印含有 NaN 的行（不影响后续，仅观察）---
    # na_mask = weekly_df[[f'{c}_lag1' for c in factor_cols] + [y_col]].isna().any(axis=1)
    # na_rows = weekly_df[na_mask]
    # logger.info("⚠️ 即将被 dropna 删除的行数: %d", len(na_rows))
    # if not na_rows.empty:
    #     # 只打印日期列，避免日志过长
    #     logger.info("被删行的日期:\n%s", na_rows[['date']].to_string())

    # 删除因滞后产生的 NaN 行（头部因为m26导致的空行将会被删除）
    # weekly_df = weekly_df.dropna(subset=[f'{c}_lag1' for c in factor_cols] + [y_col])
    # 若加上最后的y_col会导致最新日期缺少nav_return也被删除
    weekly_df = weekly_df.dropna(subset=[f'{c}_lag1' for c in factor_cols])
    # 重置索引，确保后续 iloc 正确
    #weekly_df = weekly_df.reset_index(drop=True)

    locked_date_str = experiment.get('split_cutoff_date')   # 训练集锁定日期
    if locked_date_str:
        # 已有锁定日期，按照日期划分数据集与训练集
        cutoff = pd.to_datetime(locked_date_str)
        train = weekly_df[weekly_df['date'] <= cutoff ]
        test = weekly_df[weekly_df['date'] > cutoff ]
        logger.info(f"执行增量数据分割,训练集锁定日期 {locked_date_str}")

        # 读取已有的split_ratio，防止被外部错误传入的参数更新
        split_ratio = experiment.get('split_ratio')
    else:
        # 首次分割，按照比例划分
        split_idx = int(len(weekly_df) * split_ratio)
        train = weekly_df.iloc[:split_idx].copy()
        test = weekly_df.iloc[split_idx:].copy()
        locked_date_str = str(train['date'].iloc[-1].date())

        # 写入锁定日期
        experiment_repo.update(exp_id = exp_id, split_cutoff_date = locked_date_str)
        logger.info(f"执行首次数据分割,分割比例{ split_ratio },写入锁定日期 {locked_date_str}")

    # ============================================================
    # 日志模块：记录训练/测试集划分信息
    # ============================================================
    exp_dir = get_experiment_dir(exp_id, experiment['experiment_name'], DataPathType.model)
    safe_to_csv(train, exp_dir/"train.csv")
    safe_to_csv(test, exp_dir/"test.csv")
    logger.info(f"📋 训练集与测试集已保存至 {exp_dir}")

    experiment_repo.update(exp_id,
        status=ExperimentStatus.SPLITTED,
        split_dir=get_relative_path(exp_dir),
        split_ratio=split_ratio,
        split_factor_cols=factor_cols,
        split_y_col=y_col,
        split_train_samples=len(train),
        split_test_samples=len(test),
        split_train_date_start=str(train['date'].min().date()),
        split_train_date_end=str(train['date'].max().date()),
        split_test_date_start=str(test['date'].min().date()),
        split_test_date_end=str(test['date'].max().date())
    )
    logger.info("实验 #%d 已更新分割信息", exp_id)

    ret = experiment_repo.get(exp_id=exp_id)
     # 返回关键信息
    return ret