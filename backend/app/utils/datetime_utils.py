import datetime

def ymd_to_timestamp(date_str):
    """将 '%Y-%m-%d' 格式的日期字符串转为 Unix 时间戳"""
    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    return int(dt.timestamp())