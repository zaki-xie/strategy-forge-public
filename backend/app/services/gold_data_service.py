# app/services/gold_data_service.py
import os
import pandas as pd
import logging
from pathlib import Path
from app.utils import get_process_data_dir, get_daily_1400_price

logger = logging.getLogger(__name__)

# 国际金价换算参数
USD_CNY_RATE = 7.15        # 美元兑人民币汇率（可按需修改或从配置读取）
OZ_TO_GRAM = 31.1035       # 1 盎司 = 31.1035 克

# 预处理目录中的文件名与所需列定义
PRICE_FILES = {
    "AU9999_SGE_10year_5min.csv": { # 文件名
        "date_col": "datetime",     # 日期列
        "price_cols": ["close_px"], # 价格列
        "rename": {"close_px": "AU9999_close"}  # 重命名列
    },
    "huaan_gold_etf_c_hist_df.csv": {
        "date_col": "date",
        "price_cols": ["huaan_gold_etf_price"],
        "rename": {"huaan_gold_etf_price": "ETF000217_价格"}
    },
    "fund_etf518880_tickflow.csv": {
        "date_col": "date",
        "price_cols": ["huaan_gold_etf_518880_price"],
        "rename": {"huaan_gold_etf_518880_price": "ETF518880_收盘"}
    },
    "spot_hist_sge.csv": {
        "date_col": "date",
        "price_cols": ["china_gold_spot_close"],
        "rename": {"china_gold_spot_close": "上海金交所_收盘"}
    },
    "gold_goldAPI_spot_hist_df.csv": {
        "date_col": "date",
        "price_cols": ["gold_spot_goldAPI"],
        "rename": {},
        "transform": lambda df: df.assign(
            **{"国际金价(GoldAPI)": (df["gold_spot_goldAPI"] * USD_CNY_RATE / OZ_TO_GRAM).round(4)}
        ),
        "drop_cols": ["gold_spot_goldAPI"]                         # 删除原始美元列
    }
}

def get_gold_price_timeseries(freq: str = "D") -> dict:
    """
    读取所有金价数据文件，合并为统一日期索引的时间序列。
    
    参数 
    - freq: 重采样频率，默认 'D'（日线）。高频率数据（如5分钟）会自动降采样。
    
    返回: 
     { "dates": [...], "series": { "列名": [...], ... } }
    """
    processed_dir = get_process_data_dir()
    merged = None

    for filename, meta in PRICE_FILES.items():
        filepath = processed_dir / filename
        if not filepath.exists():
            logger.warning("金价数据文件缺失: %s", filepath)
            continue

        try:
            df = pd.read_csv(filepath, parse_dates=[meta["date_col"]])
        except Exception as e:
            logger.error("读取文件失败 %s: %s", filename, e)
            continue

        # 确保日期列存在
        if meta["date_col"] not in df.columns:
            continue

        # 选取需要的价格列并重命名
        cols_to_keep = [meta["date_col"]] + meta["price_cols"]
        df_sub = df[cols_to_keep].rename(columns=meta["rename"])

        # 应用自定义转换（如国际金价换算）
        if "transform" in meta and callable(meta["transform"]):
            df_sub = meta["transform"](df_sub)

        # 删除不需要的原始列
        if "drop_cols" in meta:
            df_sub = df_sub.drop(columns=meta["drop_cols"], errors='ignore')


        df_sub = df_sub.set_index(meta["date_col"])

        # 若原始数据是多分钟线，降采样到指定频率
        # 首先判断日期时间戳类型是否符合，否则进行转换
        if freq and df_sub.index.inferred_type != "datetime64":
            df_sub.index = pd.to_datetime(df_sub.index)
        # 如果指定了频率，则执行重采样：
        # - 按 freq 频率（如 'W-FRI' 表示每周五）对数据分组
        # - .last() 取每个周期内最后一个有效值（常用于取周期末快照）
        # - .dropna() 删除重采样后产生的 NaN 行（例如某些周期无数据）
        if freq:
            df_sub = df_sub.resample(freq).last().dropna()

        if merged is None:
            merged = df_sub
        else:
            # 取并集，保留两表所有索引方式进行合并
            merged = merged.join(df_sub, how="outer")

    if merged is None:
        return {"dates": [], "series": {}}

    # 按日期排序，向前填充缺失值（可选）
    # 暂不填充查看效果
    #merged = merged.sort_index().ffill()

    # ---------- 额外加入 AU9999 每日 14:00 金价 ----------
    minute_path = processed_dir / "AU9999_SGE_10year_5min.csv"
    if minute_path.exists():
        try:
            minute_df = pd.read_csv(minute_path, parse_dates=['datetime'])
            daily_14 = get_daily_1400_price(minute_df)          # 日频 Series
            daily_14 = daily_14.dropna()

            # 根据 freq 重采样（日线无需操作）
            if freq and freq != 'D':
                daily_14 = daily_14.resample(freq).last().dropna()

            daily_14_df = daily_14.to_frame(name='AU9999_14:00价格')   # 转为 DataFrame，列名为 'AU9999_14:00价格'
            if merged is None:
                merged = daily_14_df
            else:
                merged = merged.join(daily_14_df, how="outer")
        except Exception as e:
            logger.error("提取 AU9999 14:00 价格失败: %s", e)

    if merged is None:
        return {"dates": [], "series": {}}

    merged = merged.sort_index()


    # 转换为 JSON 友好格式
    result = {
        "dates": merged.index.strftime("%Y-%m-%d").tolist(),
        "series": {}
    }
    for col in merged.columns:
        # 将 NaN 替换为 None（前端 ECharts 会自动处理 null）
        # .where(merged[col].notna(), None) 的作用：
        #   - .notna() 返回布尔 Series，标记每个元素是否非缺失（非 NaN）
        #   - .where(条件, 替代值) 表示：如果条件为 True，保留原值；否则替换为替代值（此处为 None）
        # 这样所有 NaN 值都会被替换为 Python 的 None
        # 最后 .tolist() 将 Series 转换为普通 Python 列表
        # 为什么用 None？因为 JSON 序列化时 None 会变成 null，而前端图表库（如 ECharts）通常能正确处理 null 值（显示为断点或不绘制）
        values = merged[col].where(merged[col].notna(), None).tolist()
        result["series"][col] = values

    return result