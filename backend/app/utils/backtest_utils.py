# 数据采集用相关工具函数
import os
from pathlib import Path
import re
from app.core.config import settings, BASE_DIR
import pandas as pd
import datetime
from app.schemas.enums import DataPathType
import json
from pathlib import Path
import numpy as np

# ---------- 绩效评估工具 ----------
def calc_sharpe(returns: pd.Series) -> float:
    """
    年化夏普比率 = (平均周收益率 / 周收益率标准差) * sqrt(52)
    """
    if returns.std() == 0:
        return 0.0
    return float(returns.mean() / returns.std() * np.sqrt(52))


def calc_max_drawdown(nav: pd.Series) -> float:
    """
    最大回撤 = (当前净值 / 历史最高净值 - 1) 的最小值

    表示在整个回测期间，策略净值相对于历史最高点的最大跌幅

    例如，如果某个时间点策略净值是历史最高点的80%，则回撤为 (0.8 - 1) = -0.2，即最大回撤为20%
    """
    return float((nav / nav.cummax() - 1).min())

def calc_performance(equity_df: pd.DataFrame) -> dict:
    """
    根据净值曲线 DataFrame 计算绩效指标。
    
    参数:
        equity_df: 包含 'strategy_nav', 'benchmark_nav' 列的 DataFrame
    返回:
        dict 包含年化夏普、最大回撤、年化收益率等指标
    """
    strat_nav = equity_df['strategy_nav']
    bench_nav = equity_df['benchmark_nav']

    strat_returns = strat_nav.pct_change().dropna()
    bench_returns = bench_nav.pct_change().dropna()

    # 年化夏普
    sharpe_strat = calc_sharpe(strat_returns)
    sharpe_bench = calc_sharpe(bench_returns)

    # 最大回撤
    dd_strat = calc_max_drawdown(strat_nav)
    dd_bench = calc_max_drawdown(bench_nav)

    # 年化收益率
    ann_ret_strat = float((strat_nav.iloc[-1]) ** (52 / len(strat_nav)) - 1)
    ann_ret_bench = float((bench_nav.iloc[-1]) ** (52 / len(bench_nav)) - 1)

    return {
        "strategy_sharpe": round(sharpe_strat, 2),
        "benchmark_sharpe": round(sharpe_bench, 2),
        "strategy_max_drawdown": f"{dd_strat:.2%}",
        "benchmark_max_drawdown": f"{dd_bench:.2%}",
        "strategy_annual_return": f"{ann_ret_strat:.2%}",
        "benchmark_annual_return": f"{ann_ret_bench:.2%}"
    }