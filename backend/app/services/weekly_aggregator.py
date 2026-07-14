# app/services/weekly_aggregator.py
import os
import logging
from datetime import time
import datetime
import pandas as pd
from app.core.config import settings
from app.utils import get_daily_1400_price, get_process_data_dir, get_experiment_dir, get_relative_path, safe_to_csv,  save_json, get_root_data_dir
from app.schemas.enums import DataPathType, ExperimentStatus
from app.utils.exceptions import BusinessError
from app.database.experiment_repo import experiment_repo

logger = logging.getLogger(__name__)

# ------------------------------------------------------------
# 主聚合函数
# ------------------------------------------------------------
def create_weekly_dataset(exp_id: int = None) -> dict:
    """
    执行周频数据聚合，生成 weekly_data.csv。
    若 exp_id 提供，则覆盖该实验的周频数据；否则创建新实验。
    """

    # 预处理后的数据目录
    processed_dir = get_process_data_dir()   # data/2.ProcessData
    if not processed_dir.exists():
        raise BusinessError("请先进行数据预处理")

    # 1. 加载分钟线，提取每日14:00金价
    logger.info("提取每日14:00金价...")
    minute_path = processed_dir / "AU9999_SGE_10year_5min.csv"
    minute_df = pd.read_csv(minute_path, parse_dates=['datetime'])
    daily_au = get_daily_1400_price(minute_df)          # 日频，索引为日期

    # 2. 加载联接基金净值（日频）
    logger.info("加载联接基金净值...")
    nav_path = processed_dir / "huaan_gold_etf_c_hist_df.csv"
    nav_df = pd.read_csv(nav_path, parse_dates=['date'], index_col='date')
    daily_nav = nav_df['huaan_gold_etf_nav']

    # 3. 加载其他日频数据，统一 index 为日期
    def load_series(filename, value_col, date_col='date'):
        path = processed_dir / filename
        df = pd.read_csv(path, parse_dates=[date_col], index_col=date_col)
        return df[value_col]

    logger.info("加载宏观数据...")
    daily_gold = load_series("gold_goldAPI_spot_hist_df.csv", "gold_spot_goldAPI")
    daily_dxy = load_series("dxy_yfinance_hist_df.csv", "dxy_close")
    daily_dgs10 = load_series("dgs10_hist_df.csv", "us_dgs10")
    daily_brent = load_series("Brent_hist_df.csv", "brent")
    daily_spdr = load_series("SPDR_Gold_Holdings.csv", "spdr_gold_etf_total_holding")

    # 4. 聚合为周频（取每周五的值）
    logger.info("聚合为周频...")
    weekly_au = daily_au.resample('W-FRI').last().dropna()
    weekly_nav = daily_nav.resample('W-FRI').last().dropna()
    weekly_gold = daily_gold.resample('W-FRI').last().dropna()
    weekly_dxy = daily_dxy.resample('W-FRI').last().dropna()
    weekly_dgs10 = daily_dgs10.resample('W-FRI').last().dropna()
    weekly_brent = daily_brent.resample('W-FRI').last().dropna()
    weekly_spdr = daily_spdr.resample('W-FRI').last().dropna()

    # 5. 合并并计算衍生指标
    logger.info("合并并计算指标...")
    weekly = pd.DataFrame({
        'au_1400_price': weekly_au,
        'nav': weekly_nav,
        'gold_international': weekly_gold,
        'dxy': weekly_dxy,
        'us10y': weekly_dgs10,
        'brent': weekly_brent,
        'spdr_holdings': weekly_spdr
    })

    # ---------- 校验数据完整性：基于所有日频数据的实际覆盖范围 ----------
    # 1. 收集各数据源最新有效日期
    all_last_dates = []
    for s in [daily_au, daily_nav, daily_gold, daily_dxy, daily_dgs10, daily_brent, daily_spdr]:
        if not s.empty:
            all_last_dates.append(s.dropna().index.max())
    if not all_last_dates:
        raise BusinessError("所有日频数据均为空，无法聚合")
    max_data_date = max(all_last_dates).normalize()

    # 2. 数据最大日期未达到周五，说明聚合的时候会产生未来数据，需要删除最后一周
    weekday = max_data_date.weekday()          # 0=周一，4=周五，6=周日
    if weekday < 4:
        logger.warning(
            "数据最新日期为 %s，但周频聚合的最后一周为 %s，数据不完整，移除该周",
            max_data_date.date(), weekly.index[-1].date()
        )
        weekly = weekly.iloc[:-1]

        
    # ------------------------------------------------

    # 填充低频数据
    # 部分数据更新频率低，需要前项填充
    weekly['dxy'] = weekly['dxy'].ffill()
    weekly['us10y'] = weekly['us10y'].ffill()
    weekly['brent'] = weekly['brent'].ffill()
    weekly['spdr_holdings'] = weekly['spdr_holdings'].ffill()
    weekly = weekly.dropna()

    # 调试：打印各列最新日期
    logger.info("各列最新日期：")
    for col in weekly.columns:
        last_date = weekly[col].dropna().index.max()
        logger.info(f"{col}: {last_date.date()}")

    # 周收益率
    weekly['nav_return'] = weekly['nav'].pct_change()
    weekly['au_return'] = weekly['au_1400_price'].pct_change()
    weekly['gold_int_return'] = weekly['gold_international'].pct_change()

    # SPDR持仓变化量
    weekly['spdr_change'] = weekly['spdr_holdings'].diff()

    # 趋势均线（26周）
    # 跑赢26周则为多头，否则空头
    # 计算金价趋势均线
    weekly['au_ma26'] = weekly['au_1400_price'].rolling(26).mean()
    # 趋势信号：当周14:00金价是否高于其26周均线（周五14:00可知）
    weekly['trend'] = (weekly['au_1400_price'] > weekly['au_ma26']).astype(int)

    # 净值偏离度因子（保留，用于模型预测，不做趋势判断,后续因子计算有做偏移无需担心泄露未来数据）
    weekly['nav_ma26'] = weekly['nav'].rolling(26).mean()
    weekly['deviation'] = (weekly['nav'] / weekly['nav_ma26'] - 1) * 100

    # 重置索引，保留date列
    weekly.reset_index(inplace=True)
    weekly.rename(columns={'index': 'date'}, inplace=True)


    # 9.决定使用已有实验还是新建
    if exp_id is not None:
        experiment = experiment_repo.get(exp_id)
        if not experiment:
            raise BusinessError(f"实验 #{exp_id} 不存在")
        exp_name = experiment['experiment_name']
        weekly_dir = get_experiment_dir(exp_id, exp_name, DataPathType.weekly)
        # 更新数据库状态
        experiment_repo.update(exp_id,
            status=ExperimentStatus.WEEKLY_AGGREGATOR,
            weekly_dir=get_relative_path(weekly_dir)
        )
        logger.info("覆盖实验 #%d 周频数据", exp_id)
    else:
        # 自动创建实验记录,获取exp_id
        exp_name = f"AUTO {datetime.datetime.today().strftime('%Y-%m-%d %H:%M')}"
        exp_id = experiment_repo.create(
            experiment_name = exp_name,
            status = ExperimentStatus.WEEKLY_AGGREGATOR
        )
        # 获取实验专属目录
        #exp_dir = get_experiment_dir(exp_id, exp_name, DataPathType.base)
        weekly_dir = get_experiment_dir(exp_id, exp_name, DataPathType.weekly)
         # 更新实验记录：写入 weekly_dir 相对路径
        experiment_repo.update(exp_id,
            weekly_dir=get_relative_path(weekly_dir)
        )

    # 保存周频数据
    output_path = weekly_dir / "weekly_data.csv"
    safe_to_csv(weekly, output_path)

    logger.info("实验 #%d 周频数据已保存至 %s", exp_id, output_path)

    created = experiment_repo.get(exp_id=exp_id)
    return created