# 本模块用于验证华尔街见闻返回的时间戳时区问题
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import pandas as pd
from datetime import datetime, timezone, timedelta
from app.services.wallstreetcn_kline_utils import get_parsed_kline

def verify_tz():
    # 获取今天 14:55 附近的 3 根 5 分钟 K 线
    # 如果当前时间还没到 14:55，就用昨天的同一时间
    now = datetime.now(timezone(timedelta(hours=8)))  # 北京时间
    target_time = now.replace(hour=14, minute=55, second=0, microsecond=0)
    if now < target_time:
        target_time -= timedelta(days=1)
    
    # 把北京时间转换成 UTC 时间戳（因为 API 参数 timestamp 期望的是 UTC）
    ts_for_query = int(target_time.astimezone(timezone.utc).timestamp())
    
    print(f"查询时间点（北京时间）: {target_time}")
    print(f"传递给 API 的 timestamp 参数 (UTC): {ts_for_query}")
    print()

    data = get_parsed_kline("AU9999.SGE", tick_count=3, period_type=300, timestamp=ts_for_query)
    if not data:
        print("❌ 未获取到数据，可能是非交易时段")
        return

    print("返回的 K 线数据：")
    for k in data:
        ts = k['tick_at']
        # 按 UTC 解释
        dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
        # 转为北京时间
        dt_bj = dt_utc.astimezone(timezone(timedelta(hours=8)))
        print(f"tick_at: {ts} → UTC: {dt_utc} → 北京时间: {dt_bj}")
        print(f"  收盘价: {k['close_px']}")
        print()

    print("\n请打开东方财富/同花顺，查看 Au99.99 在以下时间的 5 分钟 K 线收盘价，应该与上面基本一致。")

if __name__ == "__main__":
    verify_tz()