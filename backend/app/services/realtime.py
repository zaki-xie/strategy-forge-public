
import os
import json
import logging
import numpy as np
import pandas as pd
from datetime import datetime
from app.utils import get_experiment_dir, get_root_data_dir, safe_to_csv, save_json, get_relative_path, calc_sharpe, calc_max_drawdown, calc_performance
from app.utils.exceptions import BusinessError
from app.schemas.enums import DataPathType, ExperimentStatus
from app.database.experiment_repo import experiment_repo

logger = logging.getLogger(__name__)

def redemption_fee(hold_days: int) -> float:
    """
    根据持有天数计算卖出手续费比例
    （<7天 0.015）（<30天 0.001）
    
    :param hold_days: 持有天数
    :type hold_days: int
    :return: 手续费比例
    :rtype: float
    """
    if hold_days < 7:
        return 0.015
    elif hold_days < 30:
        return 0.001
    return 0.0

def run_realtime(
    exp_id: int = None,
    initial_cash: float = 10000.0,
    min_hold_days: int = 7
):
    """
    基于滚动OLS预测信号，执行实盘资金模拟（满仓/空仓，按周五净值成交，FIFO卖出）
    
    返回字典包含绩效、交易统计等信息，同时将结果文件写入实验目录的 4.Realtime 子目录。

    该模块依赖与滚动训练前置模块，不再强制依赖回测模块。
    
    :param exp_id: 实验编号
    :type exp_id: int
    :param initial_cash: 初始资金
    :type initial_cash: float
    :param min_hold_days: 最低持仓天数
    :type min_hold_days: int
    """
    min_hold_days = int(min_hold_days)
    initial_cash = float(initial_cash)
    # 1.前置检查
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
    if not predictions_csv.exists():
        raise BusinessError(f"缺少预测结果文件，请先执行滚动训练：{predictions_csv}")

    # 2. 尝试加载回测数据（用于三方对比，非必需）
    backtest_equityCurve = None
    backtest_dir_rel = experiment.get('backtest_dir')
    if backtest_dir_rel:
        backtest_dir = get_root_data_dir() / backtest_dir_rel
        backtest_equityCurve_csv = backtest_dir / "equity_curve.csv"
        if backtest_equityCurve_csv.exists():
            try:
                df_bt = pd.read_csv(backtest_equityCurve_csv, parse_dates=['date'])
                # all用于判断内部布尔值是否全为true
                if all(c in df_bt.columns for c in ['date', 'strategy_nav', 'benchmark_nav']):
                    backtest_equityCurve = df_bt
                else:
                    logger.warning("回测净值文件缺少必要列，跳过三方对比")
            except Exception as e:
                logger.warning("读取回测净值文件失败: %s", e)
        else:
            logger.info("回测净值文件不存在，跳过三方对比")
    else:
        logger.info("实验未执行回测，跳过三方对比")

    # 3. 加载预测数据
    logger.info("加载预测结果: %s", predictions_csv)
    test = pd.read_csv(predictions_csv, parse_dates=['date'])
    required_cols = ['date', 'signal', 'nav_return', 'nav']
    missing = [c for c in required_cols if c not in test.columns]
    if missing:
            raise BusinessError(f"预测结果缺少必要列: {missing}，请检查滚动训练输出")
    # test['signal'] = pd.to_numeric(test['signal'], errors='coerce').fillna(0).astype(int)
    # test['nav'] = pd.to_numeric(test['nav'], errors='coerce')
    
    # 信号列：必须全部可转为数值，否则中断并给出具体日期
    test['signal'] = pd.to_numeric(test['signal'], errors='coerce') # coerce模式将无法转换的值强制转换为NaN
    if test['signal'].isna().any():
        bad_dates = test.loc[test['signal'].isna(), 'date'].dt.strftime('%Y-%m-%d').tolist()
        raise BusinessError(f"信号列存在无法转换为数值的行，日期：{bad_dates}")
    test['signal'] = test['signal'].astype(int)
    
    # 净值列：允许缺失，但仅允许最后一行缺失（视为本周净值未公布），中间行缺失则报错
    test['nav'] = pd.to_numeric(test['nav'], errors='coerce')
    nav_nan = test['nav'].isna()
    if nav_nan.any():
        # 检查缺失是否只发生在最后一行
        if nav_nan.sum() > 1 or not nav_nan.iloc[-1]:
            bad_dates = test.loc[nav_nan, 'date'].dt.strftime('%Y-%m-%d').tolist()
            raise BusinessError(
                f"净值列存在异常缺失（仅允许最后一行缺失），缺失日期：{bad_dates}"
            )
        else:
            logger.info("净值最后一行为缺失（本周净值尚未公布），实盘模拟将跳过该周。")

    # 按日期排序，确保时序正确
    test = test.sort_values('date').reset_index(drop=True)

    # ============================================================
    # 实盘资金模拟（初始 10000 元，按周五净值成交 + 赎回费）
    # ============================================================
    #test: pd.DataFrame
    logger.info("开始实盘模拟。")
    cash = initial_cash # 资金
    shares = 0.0        # 份额

    # 基准买入持有：假设初始资金在第一个有效净值日全部买入，之后一直持有
    benchmark_shares = None      # 基准持有的份额，在第一个有效净值日确定
    benchmark_total_series = []  # 基准总资产序列


    # FIFO 队列：记录每笔买入的 (买入日期, 份额, 买入净值)
    fifo = []
    acct_cash_series, acct_shares_series, acct_total_series = [], [], []
    buy_dates_real, buy_prices_real, sell_dates_real, sell_prices_real = [], [], [], []
    sum_fee = 0.0   # 总手续费

    # 主循环：逐周处理信号
    for i in range(len(test)):
        nav_today = test['nav'].iloc[i]     # 本周五实际净值（结算用）
        signal = test['signal'].iloc[i]     # 本周五产生的信号
        current_date = test['date'].iloc[i]

        # 1. 计划周五下午14点执行代码，此时会缺失最后一个nav点，提前停止
        if pd.isna(nav_today):
            logger.warning(f"{current_date.date()} 净值缺失，停止实盘模拟")
            break

        # ----- 2. 根据信号执行交易（全仓/空仓） -----
        if signal == 1 and cash > 0.5:  # 买入信号：用全部现金买入，判断是否有足够现金
            buy_shares = cash / nav_today   # 计算可购买到的份额，因为all in，无需估算预计购买份额和实际购买份额的摩擦
            cash = 0.0                      # 全部购买，所以清空现金
            shares += buy_shares            # 追加持有份额
            fifo.append((current_date, buy_shares, nav_today))
            buy_dates_real.append(current_date)
            buy_prices_real.append(nav_today)

        elif signal == -1:          # 卖出信号：卖出所有可卖份额
            sellable_shares = sum(sh for bd, sh, _ in fifo if (current_date - bd).days >= min_hold_days)    # 计算可卖份额(达到持仓天数的份额)
            if sellable_shares > 0:     # 有份额可卖
                new_fifo, fee_total = [], 0.0
                for bd, sh, bn in fifo:
                    if (current_date - bd).days >= min_hold_days:
                        fee_rate = redemption_fee((current_date - bd).days)
                        fee_total += sh * nav_today * fee_rate
                    else:
                        new_fifo.append((bd, sh, bn))
                fifo = new_fifo         # 剩余持有的买入
                sum_fee += fee_total    # 累加手续费
                cash += sellable_shares * nav_today - fee_total # 卖出份额得到现金
                shares -= sellable_shares   # 剩余份额
                sell_dates_real.append(current_date)
                sell_prices_real.append(nav_today)
        # 若信号为0，不操作

        # ----- 基准买入持有 -----
        if benchmark_shares is None:
            # 第一个有效净值日：全仓买入
            benchmark_shares = initial_cash / nav_today
        benchmark_total = benchmark_shares * nav_today
        benchmark_total_series.append(benchmark_total)  # 计算基准账户价值序列

        # ----- 3. 计算本周五调仓后的持仓市值（收益结算） -----
        mkt_value = shares * nav_today  # 份额市值 = 当天交易完成后持有的份额 * 当天的净值
        total_asset = cash + mkt_value  # 总资产 = 现金+份额的市值
        # 记录本周五账户状态（调仓前）
        acct_cash_series.append(cash)               # 持有现金序列
        acct_shares_series.append(shares)           # 持有份额序列
        acct_total_series.append(total_asset)       # 账户总值序列

    logger.info("实盘模拟完成，开始统计指标。")

    
    # 4.构建账户快照历史df
    n_processed = len(acct_cash_series) # 已经模拟的周数（防止nav_today缺失导致的提前退出）
    if n_processed == 0:
        raise BusinessError(f"实盘模拟无有效周数据，检查predictions.csv的nav净值序列")
    test_processed = test.iloc[:n_processed]    # 截取已有的日期信号等用于下面生成序列

    acct_df = pd.DataFrame({
        'date': test_processed['date'],
        'cash': acct_cash_series,
        'shares': acct_shares_series,
        'total_asset': acct_total_series,
        'benchmark_total': benchmark_total_series   # 基准总资产（买入持有）
    })  # 每日账号状态

    acct_df['nav_real'] = acct_df['total_asset'] / initial_cash # 每日账户净值=总价值/起始资金
    acct_df['benchmark_nav'] = acct_df['benchmark_total'] / initial_cash

    # 5.绩效指标
    final_nav_real = acct_df['nav_real'].iloc[-1]           # 最终账户净值
    final_total_real = acct_df['total_asset'].iloc[-1]      # 最终账户总价值
    real_ret = acct_df['nav_real'].pct_change().dropna()    # 每日涨跌
    ann_ret_real = (1 + real_ret).prod() ** (52 / len(real_ret)) - 1    # 周频年化收益率,公式为：(1 + 周收益率的乘积)^(52/周数) - 1
    sharpe_real = calc_sharpe(real_ret)                 # 夏普
    dd_real = calc_max_drawdown(acct_df['nav_real'])    # 最大回撤

    # 基准买入持有绩效
    benchmark_nav_series = acct_df['benchmark_nav']
    bench_ret = benchmark_nav_series.pct_change().dropna()
    bench_ann_ret = (1 + bench_ret).prod() ** (52 / len(bench_ret)) - 1 if len(bench_ret) > 0 else None
    bench_sharpe = calc_sharpe(bench_ret) if len(bench_ret) > 0 else None
    bench_dd = calc_max_drawdown(benchmark_nav_series) if len(benchmark_nav_series) > 1 else None


    # 三方对比（如果回测数据存在）
    #diff_vs_strategy = None
    backtest_strategy_nav_end = None
    backtest_benchmark_nav_end = None
    if backtest_equityCurve is not None and len(backtest_equityCurve) > 0:
        aligned = backtest_equityCurve[backtest_equityCurve['date'].isin(test_processed['date'])]
        if len(aligned) > 0:
            backtest_strategy_nav_end = aligned['strategy_nav'].iloc[-1]
            backtest_benchmark_nav_end = round(aligned['benchmark_nav'].iloc[-1], 4)
            #diff_vs_strategy = f"{final_nav_real - last_strategy_nav:+.6f}"

    #  实盘绩效指标
    real_perf = {
        "final_total": round(final_total_real, 2),  # 最终总资产
        "final_nav": round(final_nav_real, 4),      # 最终净值
        "annual_return": f"{ann_ret_real:.2%}",     # 年化收益率
        "sharpe": round(sharpe_real, 2),            # 年化夏普
        "max_drawdown": f"{dd_real:.2%}",           # 最大回撤
        "fee_total": round(sum_fee, 2),             # 总手续费
        # 基准买入持有指标（实盘自行计算）
        "benchmark_final_total": round(benchmark_total_series[-1],2),
        "benchmark_nav_end": round(benchmark_nav_series.iloc[-1], 4),
        "benchmark_annual_return": f"{bench_ann_ret:.2%}" if bench_ann_ret is not None else None,
        "benchmark_sharpe": round(bench_sharpe, 2) if bench_sharpe is not None else None,
        "benchmark_max_drawdown": f"{bench_dd:.2%}" if bench_dd is not None else None,
        
        # 回测模块的最终净值和基准，用于三方比对
        "backtest_strategy_nav_end" : round(backtest_strategy_nav_end,4) if backtest_strategy_nav_end is not None else None,
        "backtest_benchmark_nav_end": round(backtest_benchmark_nav_end,4) if backtest_benchmark_nav_end is not None else None
    }

     # 6. 交易统计与配对
    trade_pairs = []
    n_pairs = min(len(buy_dates_real), len(sell_dates_real))
    for i in range(n_pairs):
        trade_pairs.append({
            'buy_date': buy_dates_real[i].strftime('%Y-%m-%d'),
            'buy_price': round(buy_prices_real[i], 4),
            'sell_date': sell_dates_real[i].strftime('%Y-%m-%d'),
            'sell_price': round(sell_prices_real[i], 4),
            'hold_days': (sell_dates_real[i] - buy_dates_real[i]).days
        })
    if len(buy_dates_real) > len(sell_dates_real):
        trade_pairs.append({
            'buy_date': buy_dates_real[-1].strftime('%Y-%m-%d'),
            'buy_price': round(buy_prices_real[-1], 4),
            'sell_date': None,
            'sell_price': None,
            'hold_days': None
        })

    trade_stats = {
        "buy_count": len(buy_dates_real),
        "sell_count": len(sell_dates_real),
        "total_trades": len(buy_dates_real) + len(sell_dates_real),
        "avg_hold_days": round(
            np.mean([(sell_dates_real[i] - buy_dates_real[i]).days for i in range(len(sell_dates_real))])
            if sell_dates_real else 0, 1
        ),
        "total_fee": round(sum_fee, 2),
        "signal_distribution": test['signal'].value_counts().to_dict()
    }

    # 最近5笔交易
    recent_trades = []
    for pair in trade_pairs[-5:]:
        recent_trades.append({
            'buy_date': pair['buy_date'],
            'buy_price': pair['buy_price'],
            'sell_date': pair['sell_date'] if pair['sell_date'] else '持仓中',
            'sell_price': pair['sell_price'],
            'hold_days': pair['hold_days']
        })

    # 最大回撤区间
    nav = acct_df['nav_real']
    dd_series = nav / nav.cummax() - 1  # 计算回撤序列
    max_dd_end_idx = dd_series.idxmin() # idxmin 返回回撤最深点的索引（整数索引）
    max_dd_start_idx = nav[:max_dd_end_idx].idxmax()    # 回撤起点的位置（整数索引）
    max_dd_info = {
        "start_date": acct_df.loc[max_dd_start_idx, 'date'].strftime('%Y-%m-%d'),
        "end_date": acct_df.loc[max_dd_end_idx, 'date'].strftime('%Y-%m-%d'),
        "drawdown": f"{dd_series[max_dd_end_idx]:.2%}"
    }

    # 当前账户快照
    current_account = {
        "date": acct_df['date'].iloc[-1].strftime('%Y-%m-%d'),
        "cash": round(acct_df['cash'].iloc[-1], 2),
        "shares": round(acct_df['shares'].iloc[-1], 4),
        "total_asset": round(acct_df['total_asset'].iloc[-1], 2),
        "nav_real": round(acct_df['nav_real'].iloc[-1], 4),
        "position": "持有" if acct_df['shares'].iloc[-1] > 0 else "空仓"
    }

    # 7. 输出：仅保存 CSV 文件（每日快照、全部交易记录），其余数据全部入库
    realtime_dir = get_experiment_dir(exp_id, experiment["experiment_name"], DataPathType.realtime)

    # 账户每日快照 CSV
    safe_to_csv(acct_df, realtime_dir / "account_snapshots.csv")

    # 全部交易记录 CSV
    all_trades_df = pd.DataFrame(trade_pairs)
    safe_to_csv(all_trades_df, realtime_dir / "all_trades.csv")

    # 8.更新数据库实验记录
    realtime_rel = get_relative_path(realtime_dir)
    update_data = {
        'realtime_dir': str(realtime_rel),
        'status': ExperimentStatus.REALTIMED,
        'realtime_performance_json': real_perf,          # 自动序列化
        'realtime_trade_stats_json': trade_stats,
        'realtime_max_drawdown_json': max_dd_info,
        'realtime_current_account_json': current_account,
        'realtime_recent_trades_json': recent_trades
    }
    experiment_repo.update(exp_id, **update_data)

    
    logger.info(f"实盘模拟完成，结果已保存至 {realtime_dir}")

    ret = experiment_repo.get(exp_id)
    return ret

