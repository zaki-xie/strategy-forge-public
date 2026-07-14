import pandas as pd
import logging
from app.database.experiment_repo import experiment_repo
from app.utils.data_utils import get_root_data_dir, load_json
from app.utils.exceptions import BusinessError

logger = logging.getLogger(__name__)

def get_realtime_equity_curve(exp_id: int) -> dict:
    """读取实盘模拟结果：账户快照曲线、绩效、交易统计等"""
    exp = experiment_repo.get(exp_id)
    if not exp:
        raise BusinessError(f"实验 #{exp_id} 不存在")

    realtime_dir_rel = exp.get('realtime_dir')
    if not realtime_dir_rel:
        raise BusinessError("该实验尚未执行实盘模拟")

    realtime_dir = get_root_data_dir() / realtime_dir_rel
    snapshot_file = realtime_dir / "account_snapshots.csv"
    if not snapshot_file.exists():
        raise BusinessError(f"实盘快照文件不存在: {snapshot_file}")

    # 读取每日快照
    df = pd.read_csv(snapshot_file, parse_dates=['date'])
    required = ['date', 'cash', 'shares', 'total_asset', 'benchmark_total', 'nav_real', 'benchmark_nav']
    for col in required:
        if col not in df.columns:
            raise BusinessError(f"快照文件缺少列: {col}")
    df = df.sort_values('date')

    dates = df['date'].dt.strftime('%Y-%m-%d').tolist() # 日期序列用每日快照数据日期构建
    nav_real = df['nav_real'].tolist()
    cash_series = df['cash'].tolist()
    shares_series = df['shares'].tolist()
    total_asset_series = df['total_asset'].tolist()
    benchmark_nav_series = df['benchmark_nav'].tolist() 
    benchmark_total_asset_series = df['benchmark_total'].tolist()

    # 计算实盘账户总价值回撤序列
    total_asset = df['total_asset']
    cummax = total_asset.cummax()
    dd_series = (1 - total_asset / cummax).fillna(0).tolist()

    total_asset =  df['benchmark_total']
    cummax = total_asset.cummax()
    benchmark_dd_series = (1 - total_asset / cummax).fillna(0).tolist()

    performance = exp.get('realtime_performance_json')
    # real_perf = {
    #     "final_total": round(final_total_real, 2),  # 最终总资产
    #     "final_nav": round(final_nav_real, 4),      # 最终净值
    #     "annual_return": f"{ann_ret_real:.2%}",     # 年化收益率
    #     "sharpe": round(sharpe_real, 2),            # 年化夏普
    #     "max_drawdown": f"{dd_real:.2%}",           # 最大回撤
    #     "fee_total": round(sum_fee, 2),             # 总手续费
    #     # 基准买入持有指标（实盘自行计算）
    #     "benchmark_final_total": benchmark_total_series[-1],
    #     "benchmark_annual_return": f"{bench_ann_ret:.2%}" if bench_ann_ret is not None else None,
    #     "benchmark_sharpe": round(bench_sharpe, 2) if bench_sharpe is not None else None,
    #     "benchmark_max_drawdown": f"{bench_dd:.2%}" if bench_dd is not None else None,
    #     "benchmark_nav_end": round(benchmark_nav_series.iloc[-1], 4),

    #     # 回测模块的最终净值和基准，用于三方比对
    #     "backtest_strategy_nav_end" : backtest_strategy_nav_end,
    #     "backtest_benchmark_nav_end": backtest_benchmark_nav_end
    # }

    trade_stats = exp.get('realtime_trade_stats_json')
    # trade_stats = {
    #     "buy_count": len(buy_dates_real),
    #     "sell_count": len(sell_dates_real),
    #     "total_trades": len(buy_dates_real) + len(sell_dates_real),
    #     "avg_hold_days": round(
    #         np.mean([(sell_dates_real[i] - buy_dates_real[i]).days for i in range(len(sell_dates_real))])
    #         if sell_dates_real else 0, 1
    #     ),
    #     "total_fee": round(sum_fee, 2),
    #     "signal_distribution": test['signal'].value_counts().to_dict()
    # }
    max_dd_info = exp.get('realtime_max_drawdown_json')
    # max_dd_info = {
    #     "start_date": acct_df.loc[max_dd_start_idx, 'date'].strftime('%Y-%m-%d'),
    #     "end_date": acct_df.loc[max_dd_end_idx, 'date'].strftime('%Y-%m-%d'),
    #     "drawdown": f"{dd_series[max_dd_end_idx]:.2%}"
    # }
    current_account = exp.get('realtime_current_account_json')
    # current_account = {
    #     "date": acct_df['date'].iloc[-1].strftime('%Y-%m-%d'),
    #     "cash": round(acct_df['cash'].iloc[-1], 2),
    #     "shares": round(acct_df['shares'].iloc[-1], 4),
    #     "total_asset": round(acct_df['total_asset'].iloc[-1], 2),
    #     "nav_real": round(acct_df['nav_real'].iloc[-1], 4),
    #     "position": "持有" if acct_df['shares'].iloc[-1] > 0 else "空仓"
    # }
    recent_trades = exp.get('realtime_recent_trades_json')
    # recent_trades = []
    # for pair in trade_pairs[-5:]:
    #     recent_trades.append({
    #         'buy_date': pair['buy_date'],
    #         'buy_price': pair['buy_price'],
    #         'sell_date': pair['sell_date'] if pair['sell_date'] else '持仓中',
    #         'sell_price': pair['sell_price'],
    #         'hold_days': pair['hold_days']
    #     })

     # 读取全部交易记录（用于买卖点标记）
    trades_file = realtime_dir / "all_trades.csv"
    buy_signals, sell_signals = [], []
    if trades_file.exists():
        try:
            trades_df = pd.read_csv(trades_file)
            # 买入点
            if 'buy_date' in trades_df and 'buy_price' in trades_df:
                for _, row in trades_df.iterrows():
                    buy_signals.append({
                        'date': str(row['buy_date']),
                        'price': float(row['buy_price'])
                    })
            # 卖出点（过滤 sell_date 非空）
            if 'sell_date' in trades_df and 'sell_price' in trades_df:
                for _, row in trades_df.iterrows():
                    if pd.notna(row['sell_date']) and str(row['sell_date']).strip() != '':
                        sell_signals.append({
                            'date': str(row['sell_date']),
                            'price': float(row['sell_price'])
                        })
        except Exception as e:
            logger.warning("读取交易记录 CSV 失败: %s", e)

    # 读取预测文件，获取基金净值列 (nav)
    train_dir_rel = exp.get('train_dir')
    if train_dir_rel:
        train_dir = get_root_data_dir() / train_dir_rel
        predictions_file = train_dir / "predictions.csv"
        fund_nav = []
        if predictions_file.exists():
            try:
                pred_df = pd.read_csv(predictions_file, parse_dates=['date'])
                if 'nav' in pred_df.columns and 'date' in pred_df.columns:
                    # 确保日期对齐，可能预测文件和快照文件日期不完全一致，但 nav 取值仍然可用
                    # 为安全起见，返回全量日期和 nav，前端按日期对齐
                    fund_nav_dates = pred_df['date'].dt.strftime('%Y-%m-%d').tolist()
                    fund_nav_values = pred_df['nav'].tolist()
                    # 也可以只返回与实盘日期匹配的部分，但返回全量更灵活
                    fund_nav = {
                        "dates": fund_nav_dates,
                        "values": fund_nav_values
                    }
            except Exception as e:
                logger.warning("读取预测文件基金净值失败: %s", e)
    else:
        fund_nav = None


    return {
        "dates": dates,
        "nav_real": nav_real,               # 净值曲线
        "cash": cash_series,                # 现金曲线
        "shares": shares_series,            # 份额曲线
        "total_asset": total_asset_series,  # 总资产曲线(现金+份额换算现金)
        "drawdown": dd_series,              # 回撤曲线
        "benchmark_nav": benchmark_nav_series,                   # 基准净值曲线
        "benchmark_total_asset": benchmark_total_asset_series,   # 基准资产曲线
        "benchmark_drawdown": benchmark_dd_series,                     # 基准回撤曲线
        "performance": performance,         # 绩效数据json
        "trade_stats": trade_stats,         # 实盘交易数据json
        "max_drawdown_info": max_dd_info,   # 最大回撤信息
        "current_account": current_account, # 现有账户
        "recent_trades": recent_trades,     # 最近五笔交易
        "buy_signals": buy_signals,      # 买入点
        "sell_signals": sell_signals,    # 卖出点
        "fund_nav": fund_nav,   # 基金净值曲线
    }