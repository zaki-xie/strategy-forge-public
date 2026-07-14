import pandas as pd
import logging
import json
from app.database.experiment_repo import experiment_repo
from app.utils.data_utils import get_root_data_dir
from app.utils.exceptions import BusinessError

logger = logging.getLogger(__name__)

def get_backtest_equity_curve(exp_id: int) -> dict:
    """返回回测净值曲线数据、回撤序列和数据库中的绩效摘要"""
    exp = experiment_repo.get(exp_id)
    if not exp:
        raise BusinessError(f"实验 #{exp_id} 不存在")

    backtest_dir_rel = exp.get('backtest_dir')
    if not backtest_dir_rel:
        raise BusinessError("该实验尚未完成回测")

    backtest_dir = get_root_data_dir() / backtest_dir_rel
    equity_file = backtest_dir / "equity_curve.csv"
    if not equity_file.exists():
        raise BusinessError(f"回测净值文件不存在: {equity_file}")

    # 读取净值曲线
    df = pd.read_csv(equity_file, parse_dates=['date'])
    required_cols = ['date', 'strategy_nav', 'benchmark_nav']
    if not all(col in df.columns for col in required_cols):
        raise BusinessError(f"净值文件缺少必要列，需要 {required_cols}")

    df = df.sort_values('date')
    dates = df['date'].dt.strftime('%Y-%m-%d').tolist()
    strategy_nav = df['strategy_nav'].tolist()
    benchmark_nav = df['benchmark_nav'].tolist()

    # 计算回撤序列（简单计算，数据量不大）
    strategy_cummax = df['strategy_nav'].cummax()
    benchmark_cummax = df['benchmark_nav'].cummax()
    strategy_dd = (1 - df['strategy_nav'] / strategy_cummax).fillna(0).tolist()
    benchmark_dd = (1 - df['benchmark_nav'] / benchmark_cummax).fillna(0).tolist()

    # 从数据库读取绩效指标（已由回测函数存入 backtest_performance_json）
    perf_db = exp.get('backtest_performance_json', {})
    if isinstance(perf_db, str):
        perf_db = json.loads(perf_db)   # 防御性解析

    # 数据库字段与前端需要的字段映射
    performance = {
        "strategy_total_return": perf_db.get("strategy_annual_return", None),   # 注意：数据库存的是年化收益率，前端标签可改为“年化收益”
        "benchmark_total_return": perf_db.get("benchmark_annual_return", None),
        "strategy_sharpe": perf_db.get("strategy_sharpe", None),
        "benchmark_sharpe": perf_db.get("benchmark_sharpe", None),
        "strategy_max_dd": perf_db.get("strategy_max_drawdown", None),
        "benchmark_max_dd": perf_db.get("benchmark_max_drawdown", None),
    }

     # 交易统计（直接使用数据库字段）
    buy_count = exp.get('backtest_buy_count')
    sell_count = exp.get('backtest_sell_count')
    avg_hold_days = exp.get('backtest_avg_hold_days')

    # 买卖点信号（JSON 对象，可能为字符串）
    trade_signals = exp.get('backtest_trade_signals', {})
    if isinstance(trade_signals, str):
        trade_signals = json.loads(trade_signals)

    # 最新仓位快照（JSON 对象）
    latest_snapshot = exp.get('backtest_latest_snapshot', {})
    if isinstance(latest_snapshot, str):
        latest_snapshot = json.loads(latest_snapshot)

    # 实验参数
    spilt_train_params = {
        "split_ratio": exp.get("split_ratio"),              # 训练集占比
        "ols_window": exp.get("train_ols_window"),
        "zscore_window": exp.get("train_zscore_window"),
        "buy_threshold": exp.get("train_buy_threshold"),
        "sell_threshold": exp.get("train_sell_threshold"),
        "split_cutoff_date":  exp['split_cutoff_date'],
    }

    return {
        "dates": dates,
        "strategy_nav": strategy_nav,       # 策略净值曲线
        "benchmark_nav": benchmark_nav,     # 基准净值曲线
        "strategy_dd": strategy_dd,         # 策略回撤序列
        "benchmark_dd": benchmark_dd,       # 基准回撤序列
        "performance": performance,         # 绩效指标json
        "buy_count": buy_count,             # 买入次数
        "sell_count": sell_count,           # 卖出次数
        "avg_hold_days": avg_hold_days,     # 平均持有天数
        "trade_signals": trade_signals,     # 买入卖出点
        "latest_snapshot": latest_snapshot, # 最后交易快照
        "spilt_train_params": spilt_train_params, # 数据份分割和训练参数 
    }