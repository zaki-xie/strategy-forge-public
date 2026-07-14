# app/services/data_preprocessing.py
# 数据预处理相关的服务函数
import os
import logging
import pandas as pd
from app.utils import get_process_data_dir,get_original_data_dir,safe_to_csv
from app.core.config import settings
from typing import Callable
logger = logging.getLogger(__name__)


def _clean_csv(
    src_filename: str,
    keep_columns: list[str],
    rename_map: dict[str, str] | None = None,
    extra_transforms: Callable | None = None
) -> pd.DataFrame:
    """
    通用 CSV 清洗：
    - src_filename:读取 
    - keep_columns:保留指定列
    - rename_map:重命名列信息
    - extra_transforms：可选额外转换。
    
    返回处理后的 DataFrame（不保存文件）。
    """
    original_dir = get_original_data_dir()
    df = pd.read_csv(original_dir / src_filename)
    df = df[keep_columns].copy()
    if rename_map:
        df.rename(columns=rename_map, inplace=True)
    if extra_transforms:
        df = extra_transforms(df)
    return df

def preprocess_all_data():
    """执行所有原始数据的清洗、重命名、保存到目标目录"""
    #original_dir = get_original_data_dir()# 例如 data/1.OriginalData
    target_dir = get_process_data_dir()   # 例如 data/2.ProcessData
    os.makedirs(target_dir, exist_ok=True)

    tasks = [
        # (文件名, 保留列, 重命名映射, 额外转换)
        # 1. AU9999 十年分钟线
        ("AU9999_SGE_10year_5min.csv",
         ["datetime", "open_px", "high_px", "low_px", "close_px"],
         None,
         None),
        # 2. 华安黄金ETF联接C
        ("huaan_gold_etf_c_hist_df.csv",
         ["净值日期", "单位净值"],
         {"净值日期": "date", "单位净值": "huaan_gold_etf_nav"},
         lambda df: df.assign(huaan_gold_etf_price=lambda d: (d["huaan_gold_etf_nav"] * 270).round(4))),
        # 3. 华安黄金ETF内场518880
        ("fund_etf518880_tickflow.csv",
         ["date", "close"],
         {"close": "fund_etf518880_close"},
         lambda df: df.assign(huaan_gold_etf_518880_price=lambda d: (d["fund_etf518880_close"] * 100).round(4))),
        # 4. 中国黄金现货（上交所）
        ("spot_hist_sge.csv",
         ["date", "open", "close", "low", "high"],
         {"open": "china_gold_spot_open", "close": "china_gold_spot_close",
          "low": "china_gold_spot_low", "high": "china_gold_spot_high"},
         None),
        # 5. 国际金价（GoldAPI）
        ("gold_goldAPI_spot_hist_df.csv",
         ["day", "avg_price"],
         {"day": "date", "avg_price": "gold_spot_goldAPI"},
         None),
        # 6. 美元指数（yfinance）
        ("dxy_yfinance_hist_df.csv",
         ["Date", "Close", "High", "Low", "Open", "Volume"],
         {"Date": "date", "Close": "dxy_close", "High": "dxy_high",
          "Low": "dxy_low", "Open": "dxy_open", "Volume": "dxy_volume"},
         None),
        # 7. 美国十年期国债利率
        ("dgs10_hist_df.csv",
         ["DATE", "DGS10"],
         {"DATE": "date", "DGS10": "us_dgs10"},
         None),
        # 8. 美元兑人民币
        ("usdcny_df.csv",
         ["Date", "Close", "High", "Low", "Open", "Volume"],
         {"Date": "date", "Close": "usdcny_close", "High": "usdcny_high",
          "Low": "usdcny_low", "Open": "usdcny_open", "Volume": "usdcny_volume"},
         None),
        # 9. 布伦特原油
        ("Brent_hist_df.csv",
         ["DATE", "Brent"],
         {"DATE": "date", "Brent": "brent"},
         None),
        # 10. SPDR黄金ETF持仓
        ("SPDR_Gold_Holdings.csv",
         ["日期", "总库存", "增持/减持", "总价值"],
         {"日期": "date", "总库存": "spdr_gold_etf_total_holding",
          "增持/减持": "spdr_gold_etf_holding_change", "总价值": "spdr_gold_etf_total_value"},
         None),
    ]
    for fname, keep_cols, rename_cols, extra_fn in tasks:
        df = _clean_csv(fname, keep_cols, rename_cols, extra_fn)
        safe_to_csv(df, target_dir / fname, index=False)
        logger.info(f"{fname} 处理完成")