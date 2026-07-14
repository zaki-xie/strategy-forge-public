# fileName: data_collector.py
# 数据采集服务，负责从各个数据源获取最新数据并更新本地文件
import os
import logging
import traceback
import datetime
import time
import requests
import pandas as pd
import akshare as ak
from tickflow import TickFlow
import yfinance as yf
from typing import Dict, Any
from fredapi import Fred
from contextlib import contextmanager

from app.core.config import settings
from app.utils import ymd_to_timestamp, safe_to_csv, get_original_data_dir
from app.services.wallstreetcn_kline_utils import update_kline_to_latest

# 设置日志
# __name__ 是模块名，日志输出格式包含时间、日志级别、模块名和消息内容
logger = logging.getLogger(__name__)


@contextmanager
def use_proxy():
    """临时设置代理环境变量，退出时恢复"""
    old_http = os.environ.get('HTTP_PROXY')
    old_https = os.environ.get('HTTPS_PROXY')
    try:
        if settings.HTTP_PROXY:
            os.environ['HTTP_PROXY'] = settings.HTTP_PROXY
            os.environ['HTTPS_PROXY'] = settings.HTTPS_PROXY
        yield
    finally:
        if old_http is not None:
            os.environ['HTTP_PROXY'] = old_http
        else:
            os.environ.pop('HTTP_PROXY', None)
        if old_https is not None:
            os.environ['HTTPS_PROXY'] = old_https
        else:
            os.environ.pop('HTTPS_PROXY', None)

# ------------------------------------------------------------
# 统一入口
# ------------------------------------------------------------
def update_all_data() -> Dict[str, Any]:
    """依次更新所有数据源，返回每个数据源的状态字典"""
    result = {}
    data_dir = get_original_data_dir()

    funcs = {
        "Au99.99分钟线": lambda: update_kline_to_latest(
            "AU9999.SGE",
            os.path.join(data_dir, "AU9999_SGE_10year_5min.csv"),
            period_type=300
        ),
        "Au99.99现货": lambda: update_spot_hist_sge(
            os.path.join(data_dir, "spot_hist_sge.csv")
        ),
        "000217净值": lambda: update_huaan_nav(
            os.path.join(data_dir, "huaan_gold_etf_c_hist_df.csv")
        ),
        "518880行情": lambda: update_518880_daily(
            os.path.join(data_dir, "fund_etf518880_tickflow.csv")
        ),
        "国际金价(GoldAPI)": lambda: update_gold_goldAPI_spot(
            os.path.join(data_dir, "gold_goldAPI_spot_hist_df.csv")
        ),
        "美元指数": lambda: update_dxy_yfinance(
            os.path.join(data_dir, "dxy_yfinance_hist_df.csv")
        ),
        "美债10年期利率": lambda: update_dgs10(
            os.path.join(data_dir, "dgs10_hist_df.csv")
        ),
        "美元兑人民币": lambda: update_usdcny(
            os.path.join(data_dir, "usdcny_df.csv")
        ),
        "布伦特原油": lambda: update_brent(
            os.path.join(data_dir, "Brent_hist_df.csv")
        ),
        "SPDR持仓": lambda: update_spdr_gold_holdings(
            os.path.join(data_dir, "SPDR_Gold_Holdings.csv")
        ),
    }

    for name, func in funcs.items():
        try:
            func()
            result[name] = "success"
        except Exception as e:
            logger.error("更新 %s 失败: %s\n%s", name, e, traceback.format_exc())
            result[name] = f"failed: {str(e)}"

    return result

# 1、爬虫抓取华尔街见闻K线
# 见wallstreetcn_kline_utils.py

# ------------------------------------------------------------
# 2、华安黄金ETF联接C（000217）净值
# ------------------------------------------------------------
# huaan_gold_etf_c_hist_df.csv
# 当天净值当天晚上不公开，之前没考虑到，28号只公开到27的净值
def update_huaan_nav(filename: str):
    """
    增量更新华安黄金ETF联接C（000217）单位净值原始数据。
    - 保持原始列名不变：['净值日期', '单位净值', '日增长率']
    - 合并新旧数据，重复日期保留 AKShare 最新值
    - 覆盖保存到原文件
    """
    # 1. 从 AKShare 拉取全部历史数据
    logger.info("正在获取 000217 最新净值数据...")
    try:
        df_new = ak.fund_open_fund_info_em(symbol="000217", indicator="单位净值走势")
    except Exception as e:
        logger.error("获取 000217 净值失败: %s", e)
        return

    # 2. 统一日期格式
    df_new["净值日期"] = pd.to_datetime(df_new["净值日期"])

    # 3. 处理本地已有文件
    if os.path.exists(filename):
        logger.info("发现本地文件 %s，合并新旧数据...", filename)
        df_old = pd.read_csv(filename, parse_dates=["净值日期"])
        # 合并，按「净值日期」去重，保留新数据
        df_combined = pd.concat([df_old, df_new], ignore_index=True)
        df_combined.drop_duplicates(subset=["净值日期"], keep="last", inplace=True)
        df_combined.sort_values("净值日期", inplace=True)
    else:
        logger.info("本地文件不存在，创建新文件 %s", filename)
        df_combined = df_new.sort_values("净值日期")

    # 4. 保存（保持原始列名，不添加任何衍生列）
    safe_to_csv(df_combined, filename, index=False, encoding="utf-8-sig")
    logger.info("更新完成！数据范围: %s ~ %s，共 %d 条",
                df_combined["净值日期"].iloc[0].date(),
                df_combined["净值日期"].iloc[-1].date(),
                len(df_combined))
    return df_combined

# ------------------------------------------------------------
# 3、华安黄金ETF 518880 日K线（TickFlow）
# ------------------------------------------------------------
# 备用方案tickFlow API，可免费拉取大A日K
def fetch_all_518880_daily(filename: str):
    """
    一次性获取 518880 全部历史日 K 线（保留所有字段）。
    额外添加北京时间日期列 'date'，按 date 排序去重。
    """
    logger.info("正在全量获取 518880 日K线（最多10000条）...")
    with TickFlow.free() as tf:
        df = tf.klines.get("518880.SH", period="1d", count=10000, as_dataframe=True)

        # 转换 UTC 毫秒时间戳为北京时间日期
        df["date"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True) \
                    .dt.tz_convert("Asia/Shanghai").dt.date
        df["date"] = pd.to_datetime(df["date"])

        # 按日期排序并去重（保留最新数据）
        df = df.sort_values("date").drop_duplicates(subset=["date"], keep="last")

        # 保存全部字段（包括原始 timestamp 和新增的 date）
        safe_to_csv(df, filename, index=False, encoding="utf-8-sig")
        logger.info("全量数据已保存至 %s，共 %d 条", filename, len(df))
    return df


def update_518880_daily(filename: str):
    """
    增量更新 518880 日 K 线数据（只合并 TickFlow 自身数据）。
    - 读取本地文件最新日期，只拉取缺失的日期段。
    - 合并新旧数据，按 date 去重（保留新值），保存所有字段。
    """
    # 1. 读取本地文件（已经是 TickFlow 格式，列名包含 date, timestamp, open, high, low, close, volume, ...）
    if os.path.exists(filename):
        df_old = pd.read_csv(filename, parse_dates=["date"])
        latest_date = df_old["date"].max()
        start_date = latest_date + pd.Timedelta(days=1)
        logger.info("本地最新: %s，将从 %s 开始获取新数据", latest_date.date(), start_date.date())
    else:
        logger.info("本地文件不存在，全量获取。")
        return fetch_all_518880_daily(filename)

    end_date = datetime.date.today()
    if start_date.date() > end_date:
        logger.info("数据已是最新，无需更新。")
        return df_old

    # 2. 拉取新数据（起始时间用毫秒时间戳）
    start_ms = int(pd.Timestamp(start_date).timestamp() * 1000)
    logger.info("正在获取 518880 日K线，范围: %s ~ %s", start_date.date(), end_date)

    with TickFlow.free() as tf:
        new = tf.klines.get("518880.SH", period="1d", start_time=start_ms, count=10000, as_dataframe=True)

        if new.empty:
            print("无新数据。")
            return df_old

        # 转换时间戳并添加 date 列（与全量拉取逻辑一致）
        new["date"] = pd.to_datetime(new["timestamp"], unit="ms", utc=True) \
                    .dt.tz_convert("Asia/Shanghai").dt.date
        new["date"] = pd.to_datetime(new["date"])

        # 按日期去重
        new = new.sort_values("date").drop_duplicates(subset=["date"], keep="last")

        # 3. 合并新旧数据（直接 concat，按 date 去重）
        combined = pd.concat([df_old, new], ignore_index=True)
        combined = combined.sort_values("date").drop_duplicates(subset=["date"], keep="last")
        combined = combined.dropna(subset=["date"])

        # 4. 保存（保留所有列，包括 timestamp）
        safe_to_csv(combined, filename, index=False, encoding="utf-8-sig")
        logger.info("更新完成！数据范围: %s ~ %s，共 %d 条",
                    combined["date"].iloc[0].date(),
                    combined["date"].iloc[-1].date(),
                    len(combined))
    return combined

# ------------------------------------------------------------
# 4、中国黄金现货（Au99.99 日线）
# ------------------------------------------------------------
# spot_hist_sge.csv
def update_spot_hist_sge(filename: str):
    """更新 Au99.99 现货历史日线数据（全量拉取 + 合并去重）"""
    logger.info("正在获取 Au99.99 全部历史数据...")
    df_new = ak.spot_hist_sge(symbol='Au99.99')
    df_new["date"] = pd.to_datetime(df_new["date"])

    if os.path.exists(filename):
        df_old = pd.read_csv(filename, parse_dates=["date"])
        df_combined = pd.concat([df_old, df_new], ignore_index=True)
        df_combined.drop_duplicates(subset=["date"], keep="last", inplace=True)
        df_combined.sort_values("date", inplace=True)
    else:
        df_combined = df_new.sort_values("date")

    safe_to_csv(df_combined, filename, index=False, encoding="utf-8-sig")
    logger.info("更新完成！%s ~ %s，共 %d 条",
                df_combined["date"].iloc[0].date(),
                df_combined["date"].iloc[-1].date(),
                len(df_combined))
    return df_combined


# ------------------------------------------------------------
# 5、国际金价（GoldAPI）
# ------------------------------------------------------------
# gold_goldAPI_spot_hist_df.csv
# 该接口晚上无法获得到当天价格，例如28号晚上21点仍然获取不到28号当天数据
def update_gold_goldAPI_spot(filename: str):
    """
    增量更新国际金价（GoldAPI）日线数据。
    - 读取本地文件最新日期，只拉取此后至今的数据。
    - 合并新旧数据，重复日期保留 API 最新值（覆盖旧数据）。
    - 保持原始列名不变：['avg_price', 'day']
    """
    api_key = settings.GOLD_API_KEY
    if not api_key:
        raise ValueError("GOLD_API_KEY 未配置")

    # 代理配置（仅对本函数内的 requests 调用生效）
    proxies = None
    if settings.HTTP_PROXY:
        proxies = {"http": settings.HTTP_PROXY, "https": settings.HTTPS_PROXY}

    # 构造请求头
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "Origin": "https://gold-api.com",
        "Referer": "https://gold-api.com/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
        "sec-ch-ua": "\"Microsoft Edge\";v=\"147\", \"Not/A.Brand\";v=\"8\", \"Chromium\";v=\"147\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "x-api-key": api_key
    }
    
    # 1. 确定起始日期：本地文件最新日期的次日
    if os.path.exists(filename):
        df_old = pd.read_csv(filename, parse_dates=["day"])
        latest_date = df_old["day"].max()
        start_date = (latest_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        logger.info("本地最新: %s，将从 %s 开始获取新数据", latest_date.date(), start_date)
    else:
        # 文件不存在，从最早日期开始拉取（2000-01-01）
        start_date = "2000-01-01"
        df_old = pd.DataFrame()  # 空 DataFrame 用于后续合并
        logger.info("本地文件不存在，将获取全部历史数据")
    
    end_date = datetime.datetime.today().strftime("%Y-%m-%d")
    
    # 2. 检查是否需要更新
    if start_date > end_date:
        logger.info("数据已是最新，无需更新。")
        return df_old if not df_old.empty else None
    
    # 3. 构造请求参数
    url = "https://api.gold-api.com/history"
    params = {
        "symbol": "XAU",
        "groupBy": "day",
        "startTimestamp": ymd_to_timestamp(start_date),
        "endTimestamp": ymd_to_timestamp(end_date),
        "aggregation": "avg",
        "orderBy": "asc"
    }
    
    logger.info("正在获取国际金价数据，范围: %s ~ %s", start_date, end_date)
    resp  = requests.get(url, params=params, headers=headers, proxies=proxies)
    resp.raise_for_status() # 如果响应状态码不是 200，会抛出异常
    data = resp.json()
    df_new = pd.DataFrame(data)
    if df_new.empty:
        logger.info("无新数据。")
        return df_old if not df_old.empty else None
    
    df_new["day"] = pd.to_datetime(df_new["day"])
    df_new.sort_values("day", inplace=True)
    logger.info("获取到 %d 条新数据", len(df_new))

    # 4. 合并新旧数据
    if not df_old.empty:
        df_combined = pd.concat([df_old, df_new], ignore_index=True)
        df_combined.drop_duplicates(subset=["day"], keep="last", inplace=True)
        df_combined.sort_values("day", inplace=True)
    else:
        df_combined = df_new
    
    # 5. 保存
    safe_to_csv(df_combined, filename, index=False, encoding="utf-8-sig")
    logger.info("更新完成！%s ~ %s，共 %d 条",
            df_combined["day"].iloc[0].date(),
            df_combined["day"].iloc[-1].date(),
            len(df_combined))
    return df_combined

# ------------------------------------------------------------
# 6、美元指数（yfinance）
# ------------------------------------------------------------
#  dxy_yfinance_hist_df.csv
def update_dxy_yfinance(filename: str):
    """增量更新美元指数，列名统一为简单格式，与旧 CSV 一致"""
    # 1. 读取旧数据
    if os.path.exists(filename):
        df_old = pd.read_csv(filename, parse_dates=["Date"])
        latest_date = df_old["Date"].max()
        start = latest_date + pd.Timedelta(days=1)
        logger.info("本地最新: %s，从 %s 开始拉取", latest_date.date(), start.date())
    else:
        start = datetime.datetime(1962, 1, 2)
        df_old = pd.DataFrame()

    end = datetime.datetime.today()
    if start > end:
        logger.info("已是最新，无需更新。")
        return df_old if not df_old.empty else None

    max_retries = 3

    with use_proxy(): # 代理
        for attempt in range(max_retries):
            try:
                # 2. 下载新数据
                logger.info("下载 DXY: %s ~ %s (尝试 %d/%d)", start.date(), end.date(), attempt+1, max_retries)
                new = yf.download("DX-Y.NYB", interval="1d", start=start, end=end, progress=False) # progress关闭进度条
                new = new.reset_index()
                if new.empty:
                    logger.warning("未下载到任何数据（可能限流），等待后重试...")
                    time.sleep(10)  # 限流后退避
                    continue

                # 如果是 MultiIndex，提取第一层
                if isinstance(new.columns, pd.MultiIndex):
                    new.columns = new.columns.get_level_values(0)
                # 统一列名
                expected_cols = ["Date", "Close", "High", "Low", "Open", "Volume"]
                if set(expected_cols).issubset(set(new.columns)):
                    new = new.reset_index()[expected_cols]
                    new["Date"] = pd.to_datetime(new["Date"])
                    break  # 成功
                else:
                    logger.error("下载的列名不匹配：%s", new.columns)
                    return df_old if not df_old.empty else None
            except Exception as e:
                logger.error("下载 DXY 失败: %s", e)
                if attempt < max_retries - 1:
                    time.sleep(10)
                else:
                    # 所有重试失败，返回旧数据
                    logger.warning("多次尝试后仍无法下载，保留旧数据。")
                    return df_old if not df_old.empty else None


        # 3. 合并、去重、排序
        combined = pd.concat([df_old, new], ignore_index=True)
        combined.drop_duplicates(subset=["Date"], keep="last", inplace=True)
        combined.sort_values("Date", inplace=True)
        combined = combined.dropna(subset=["Date"])

        # 4. 保存（普通 CSV，单行列名）
        safe_to_csv(combined, filename, index=False, encoding="utf-8-sig")
        logger.info("更新完成！%s ~ %s，共 %d 条",
                combined["Date"].iloc[0].date(),
                combined["Date"].iloc[-1].date(),
                len(combined))
        return combined

# ------------------------------------------------------------
# 7、美国十年期国债利率
# ------------------------------------------------------------
# gs10_hist_df.csv
# 该数据更新不及时，28号晚上只能拉到26号的数据，还有数据丢失问题比如25号数据不存在
# 查询了FRED，他们的数据就是这样的
# 数据源挂掉了，获取不到20260606
def update_dgs10(filename: str):
    """增量更新美债10年期利率（DGS10），使用 FRED API"""
    if not settings.FRED_API_KEY:
        logger.error("FRED_API_KEY 未配置，无法更新 DGS10 数据")
        return None

    # 1. 确定起始日期
    if os.path.exists(filename):
        df_old = pd.read_csv(filename, parse_dates=["DATE"])
        latest_date = df_old["DATE"].max()
        start = latest_date + pd.Timedelta(days=1)
        logger.info("本地最新: %s，从 %s 开始拉取", latest_date.date(), start.date())
    else:
        start = datetime.datetime(1962, 1, 2)
        df_old = pd.DataFrame()

    end = datetime.datetime.today()
    if start > end:
        logger.info("已是最新，无需更新。")
        return df_old if not df_old.empty else None

    fred = Fred(api_key=settings.FRED_API_KEY)
    logger.info("下载 DGS10: %s ~ %s", start.date(), end.date())
    try:
        series = fred.get_series('DGS10', observation_start=start, observation_end=end)
        df_new = series.reset_index()
        df_new.columns = ["DATE", "DGS10"]
        df_new["DATE"] = pd.to_datetime(df_new["DATE"])
        df_new["DGS10"] = pd.to_numeric(df_new["DGS10"], errors="coerce")
        df_new.dropna(subset=["DGS10"], inplace=True)
    except Exception as e:
        logger.error("下载 DGS10 失败: %s", e)
        return df_old if not df_old.empty else None

    if df_new.empty:
        logger.info("无新数据。")
        return df_old if not df_old.empty else None

    combined = pd.concat([df_old, df_new], ignore_index=True)
    combined.drop_duplicates(subset=["DATE"], keep="last", inplace=True)
    combined.sort_values("DATE", inplace=True)
    combined = combined.dropna(subset=["DATE"])
    safe_to_csv(combined, filename, index=False, encoding="utf-8-sig")
    logger.info("更新完成！%s ~ %s，共 %d 条",
                combined["DATE"].iloc[0].date(),
                combined["DATE"].iloc[-1].date(),
                len(combined))
    return combined

# ------------------------------------------------------------
# 8、美元兑人民币（yfinance）
# ------------------------------------------------------------
# usdcny_df.csv
def update_usdcny(filename: str):
    """增量更新美元兑人民币（CNY=X），列名统一为简单格式"""
    # 1. 读取旧文件，确定起始日期
    if os.path.exists(filename):
        df_old = pd.read_csv(filename, parse_dates=["Date"])
        latest_date = df_old["Date"].max()
        start = latest_date + pd.Timedelta(days=1)
        logger.info("本地最新: %s，从 %s 开始拉取", latest_date.date(), start.date())
    else:
        start = datetime.datetime(1962, 1, 2)
        df_old = pd.DataFrame()

    end = datetime.datetime.today()
    if start > end:
        logger.info("已是最新，无需更新。")
        return df_old if not df_old.empty else None

    # 2. 下载新数据，统一列名
    with use_proxy():
        logger.info("下载 CNY: %s ~ %s", start.date(), end.date())
        new = yf.download("CNY=X", interval="1d", start=start, end=end)
        new.reset_index(inplace=True)
        new.columns = ['Date', 'Close', 'High', 'Low', 'Open', 'Volume']
        new["Date"] = pd.to_datetime(new["Date"])

        if new.empty:
            logger.info("无新数据。")
            return df_old if not df_old.empty else None

        # 3. 合并、去重、排序
        combined = pd.concat([df_old, new], ignore_index=True)
        combined.drop_duplicates(subset=["Date"], keep="last", inplace=True)
        combined.sort_values("Date", inplace=True)
        combined = combined.dropna(subset=["Date"])

        # 4. 保存
        safe_to_csv(combined, filename, index=False, encoding="utf-8-sig")
        logger.info("更新完成！%s ~ %s，共 %d 条",
                    combined["Date"].iloc[0].date(),
                    combined["Date"].iloc[-1].date(),
                    len(combined))
        return combined

# ------------------------------------------------------------
# 9、布伦特原油
# ------------------------------------------------------------
# Brent_hist_df.csv
# 数据更新频率较低，官方数据就是这样的
# web工具或者frend挂掉了
def update_brent(filename: str):
    """增量更新布伦特原油现货价格（DCOILBRENTEU），使用 FRED API"""
    if not settings.FRED_API_KEY:
        logger.error("FRED_API_KEY 未配置，无法更新布伦特原油数据")
        return None

    # 1. 确定起始日期
    if os.path.exists(filename):
        df_old = pd.read_csv(filename, parse_dates=["DATE"])
        latest_date = df_old["DATE"].max()
        start = latest_date + pd.Timedelta(days=1)
        logger.info("本地最新: %s，从 %s 开始拉取", latest_date.date(), start.date())
    else:
        start = datetime.datetime(1987, 5, 20)
        df_old = pd.DataFrame()

    end = datetime.datetime.today()
    if start > end:
        logger.info("已是最新，无需更新。")
        return df_old if not df_old.empty else None

    # 2. 创建 Fred 实例（默认使用系统代理或不使用代理，根据网络环境决定）
    fred = Fred(api_key=settings.FRED_API_KEY)
    # 如需设置超时，可取消下行注释
    # fred.session.timeout = 120

    # 3. 获取数据
    logger.info("下载 Brent: %s ~ %s", start.date(), end.date())
    try:
        series = fred.get_series('DCOILBRENTEU', observation_start=start, observation_end=end)
        df_new = series.reset_index()
        df_new.columns = ["DATE", "Brent"]
        df_new["DATE"] = pd.to_datetime(df_new["DATE"])
        df_new["Brent"] = pd.to_numeric(df_new["Brent"], errors="coerce")
        df_new.dropna(subset=["Brent"], inplace=True)
    except Exception as e:
        logger.error("下载 Brent 失败: %s", e)
        return df_old if not df_old.empty else None

    if df_new.empty:
        logger.info("无新数据。")
        return df_old if not df_old.empty else None

    # 4. 合并、去重、排序
    combined = pd.concat([df_old, df_new], ignore_index=True)
    combined.drop_duplicates(subset=["DATE"], keep="last", inplace=True)
    combined.sort_values("DATE", inplace=True)
    combined = combined.dropna(subset=["DATE"])

    # 5. 保存
    safe_to_csv(combined, filename, index=False, encoding="utf-8-sig")
    logger.info("更新完成！%s ~ %s，共 %d 条",
                combined["DATE"].iloc[0].date(),
                combined["DATE"].iloc[-1].date(),
                len(combined))
    return combined

# ------------------------------------------------------------
# 10、SPDR黄金ETF持仓
# ------------------------------------------------------------
# SPDR_Gold_Holdings.csv
# 接口存在稳定性问题，接口数据更新频率低，28号只能拿到22号
def update_spdr_gold_holdings(filename: str):
    """增量更新 SPDR 黄金 ETF 持仓数据（全量拉取 + 合并去重）"""
    # 1. 读取本地旧文件，获取最新日期
    date_col = None
    if os.path.exists(filename):
        df_old = pd.read_csv(filename)
        # 自动识别日期列（常见列名：日期, date, Date, DATE）
        for col in ['日期', 'date', 'Date', 'DATE']:
            if col in df_old.columns:
                date_col = col
                df_old[col] = pd.to_datetime(df_old[col])
                latest_date = df_old[col].max()
                logger.info("本地最新日期: %s", df_old[col].max().date())
                break
        if date_col is None:
            logger.warning("未找到日期列，将重新下载全量数据。")
            df_old = pd.DataFrame()
    else:
        df_old = pd.DataFrame()
        logger.info("本地文件不存在，将下载全量数据。")

    # 2. 下载新数据（全量）
    logger.info("正在从 AKShare 获取 SPDR 黄金持仓数据...")
    try:
        df_new = ak.macro_cons_gold()
    except Exception as e:
        logger.error("获取 SPDR 数据失败: %s", e)
        return

    if df_new.empty:
        logger.info("未获取到新数据。")
        return

    # 3. 统一日期列
    if date_col is None:
        # 未从旧文件找到日期列，从新数据中识别
        for col in ['日期', 'date', 'Date', 'DATE']:
            if col in df_new.columns:
                date_col = col
                break
    if date_col is None:
        raise ValueError("无法找到日期列，请检查数据格式。")

    df_new[date_col] = pd.to_datetime(df_new[date_col])

    # 4. 合并新旧数据
    if not df_old.empty:
        df_combined = pd.concat([df_old, df_new], ignore_index=True)
        df_combined.drop_duplicates(subset=[date_col], keep="last", inplace=True)
        df_combined.sort_values(date_col, inplace=True)
    else:
        df_combined = df_new.sort_values(date_col)

    # 5. 保存（保持原始列名不变）
    safe_to_csv(df_combined, filename, index=False, encoding="utf-8-sig")
    logger.info("更新完成！%s ~ %s，共 %d 条",
            df_combined[date_col].iloc[0].date(),
            df_combined[date_col].iloc[-1].date(),
            len(df_combined))
    return df_combined

