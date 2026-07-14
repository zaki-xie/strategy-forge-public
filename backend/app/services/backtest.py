# app/services/backtest.py
import os
import json
import logging
import datetime
import numpy as np
import pandas as pd
from app.core.config import settings
from app.utils import get_experiment_dir, get_root_data_dir, safe_to_csv, save_json, get_relative_path, calc_sharpe, calc_max_drawdown, calc_performance
from app.utils.exceptions import BusinessError
from app.schemas.enums import DataPathType, ExperimentStatus
from app.database.experiment_repo import experiment_repo

logger = logging.getLogger(__name__)

def run_backtest(
    exp_id: int = None
) -> dict:
    """
    基于滚动 OLS 生成的预测信号，执行周频回测模拟。
    
    参数:
        exp_id: 实验编号

    返回:
        dict 包含回测绩效指标和文件路径
    """
    # 前置检查
    if exp_id is None:
        raise BusinessError(f"实验ID不可为空")
    
    experiment = experiment_repo.get(exp_id=exp_id)
    if experiment is None:
        raise BusinessError(f"实验记录不存在")

    train_rel = experiment.get('train_dir')
    status : ExperimentStatus = experiment.get('status')
    if not train_rel and status !=  ExperimentStatus.TRAINED:
        raise BusinessError("该实验尚未完成训练")
    train_dir = get_root_data_dir() / train_rel

    predictions_csv = train_dir / "predictions.csv"    
    if not os.path.exists(predictions_csv):
        raise BusinessError(f"缺少预测结果文件，请先执行滚动训练：{predictions_csv}")

    # 加载数据
    logger.info("加载预测结果: %s", predictions_csv)
    test = pd.read_csv(predictions_csv, parse_dates=['date'])
    required_cols = ['date', 'signal', 'nav_return']
    for col in required_cols:
        if col not in test.columns:
            raise BusinessError(f"预测结果缺少必要列: {col}，请检查滚动训练输出")

    # -------- 回测模拟 --------
    strategy_nav = [1.0]    # 策略净值，初始值为1
    benchmark_nav = [1.0]   # 买入持有净值（如果我从一开始就满仓持有到现在，会有吊烧收益）
    position = 0.0          # 当前仓位，起始空仓

    # 记录买卖点
    buy_dates, buy_prices = [], []
    sell_dates, sell_prices = [], []
    trade_pairs = []          # 记录已完成交易对
    pending_buy = None        # 临时存储未配对的买入


    for i in range(len(test)):
        # 本周收益率
        weekly_ret = test['nav_return'].iloc[i]
        if pd.isna(weekly_ret):
            weekly_ret = 0.0

        # 策略收益 = 仓位 × 周收益
        strategy_ret = position * weekly_ret
        strategy_nav.append(strategy_nav[-1] * (1 + strategy_ret))
        # 基准买入持有收益
        benchmark_nav.append(benchmark_nav[-1] * (1 + weekly_ret))

        # 本周仓位由本周信号决定
        # （本周信号是在本周收盘前就能知道的，因为因子是上周的）
        signal = test['signal'].iloc[i]
        prev_position = position
        if signal == 1:
            position = 1.0
        elif signal == -1:
            position = 0.0
        # else 维持原仓位

        # 记录买卖点（当仓位发生改变时）
        if position != prev_position:
            current_nav = strategy_nav[-1]              # 调仓后的净值
            if position == 1.0:                         # 刚买入
                buy_dates.append(test['date'].iloc[i])
                buy_prices.append(current_nav)
                
                # 记录买入点
                pending_buy = {
                    'buy_date': test['date'].iloc[i],
                    'buy_price': current_nav
                }
            elif position == 0.0:                       # 刚卖出
                sell_dates.append(test['date'].iloc[i])
                sell_prices.append(current_nav)

                # 配对：找到最近一次买入
                if pending_buy is not None:
                    trade_pairs.append({
                        'buy_date': pending_buy['buy_date'],
                        'buy_price': pending_buy['buy_price'],
                        'sell_date': test['date'].iloc[i],
                        'sell_price': current_nav,
                        'hold_days': (test['date'].iloc[i] - pending_buy['buy_date']).days
                    })
                    pending_buy = None

    # 去掉初始的1.0，长度对齐 test
    test['strategy_nav'] = strategy_nav[1:]
    test['benchmark_nav'] = benchmark_nav[1:]

    # -------- 保存结果 --------
    output_dir = get_experiment_dir(exp_id, experiment["experiment_name"], DataPathType.backtest)

    # 1. 保存净值曲线（周频）
    nav_df = test[['date', 'strategy_nav', 'benchmark_nav']].copy()
    nav_path = output_dir/"equity_curve.csv"
    safe_to_csv(nav_df, nav_path)
    logger.info("净值曲线已保存至 %s", nav_path)

    # 2.绩效指标
    perf = calc_performance(test[['date', 'strategy_nav', 'benchmark_nav']])
    # perf_path = output_dir/"performance.json"
    # save_json(perf, perf_path)
    # logger.info("绩效指标已保存至 %s", perf_path)

    # 3. 买卖点
    trade_points = {
        "buy": [{"date": str(d.date()), "price": p} for d, p in zip(buy_dates, buy_prices)],
        "sell": [{"date": str(d.date()), "price": p} for d, p in zip(sell_dates, sell_prices)]
    }
    # trade_path = output_dir/"trade_signals.json"
    # save_json(trade_points, trade_path)
    # logger.info("买卖点已保存至 %s", trade_path)

    # 4. 当前仓位快照
    current_holding = "满仓" if position == 1.0 else "空仓"
    latest_snapshot = {
        "date": str(test['date'].iloc[-1].date()),                          # 最后一期对应的日期
        "signal": int(test['signal'].iloc[-1]),                             # 最后一期的信号（决定下周操作）
        "current_position": current_holding,                                # 当前（本周）实际仓位
        "position_value": position,                                         # 数值仓位（1.0 或 0.0）
        "strategy_nav": round(float(test['strategy_nav'].iloc[-1]), 4),     # 当前策略净值
        "benchmark_nav": round(float(test['benchmark_nav'].iloc[-1]), 4)    # 当前基准净值
    }
    # snapshot_path = output_dir/"latest_position.json"
    # save_json(latest_snapshot, snapshot_path)
    # logger.info("仓位快照已保存至 %s", snapshot_path)

    # 5. 计算买入次数、卖出次数、平均持有天数
    buy_count = len(buy_dates)
    sell_count = len(sell_dates)
    avg_hold_days = None
    if trade_pairs:  # trade_pairs 是从回测循环中收集的买卖配对列表
        hold_days = [(p['sell_date'] - p['buy_date']).days for p in trade_pairs]
        avg_hold_days = sum(hold_days) / len(hold_days)

    # -------- 计算并保存绩效指标 --------
    
    experiment_repo.update(exp_id,
        status=ExperimentStatus.BACKTESTED,
        backtest_dir = get_relative_path(output_dir),   # 净值曲线路径
        backtest_performance_json = perf,               # 绩效指标
        backtest_trade_signals = trade_points,          # 买入点和卖出点
        backtest_latest_snapshot = latest_snapshot,     # 最后仓位快照
        backtest_buy_count = buy_count,                 # 买入次数
        backtest_sell_count = sell_count,               # 卖出次数
        backtest_avg_hold_days = avg_hold_days          # 平均持有天数
    )

    ret = experiment_repo.get(exp_id)
    return ret




