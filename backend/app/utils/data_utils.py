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


def _ensure_absolute(data_dir: str) -> Path:
    """将配置中的 DATA_DIR 转为绝对路径。
    - 若已是绝对路径，直接返回；
    - 若是相对路径，则相对于项目根目录 BASE_DIR 拼接。
    """
    p = Path(data_dir)
    if p.is_absolute():
        return p
    return BASE_DIR / p

def get_root_data_dir():
    """获取数据存储根目录settings.DATA_DIR"""
    return _ensure_absolute(settings.DATA_DIR).resolve()

def get_original_data_dir():
    """获取路径settings.DATA_DIR / "1.OriginalData"""
    return _ensure_absolute(settings.DATA_DIR).resolve() / "1.OriginalData"

def get_process_data_dir():
    """获取路径settings.DATA_DIR / "2.ProcessData"""
    return _ensure_absolute(settings.DATA_DIR).resolve() / "2.ProcessData"

def get_experiment_root_dir():
    """获取路径settings.DATA_DIR / "3.Experiment"""
    return _ensure_absolute(settings.DATA_DIR).resolve() / "3.Experiment"

def get_experiment_dir(exp_id: int, experiment_name: str = "exp", path_type: DataPathType = DataPathType.base) -> Path:
    """
    获取某个实验的专属目录路径。
    目录名格式：{exp_id}_{experiment_name}
    例如：3.Experiment/23_AUTO-2026-06-17/
    """
    # 清理名称中的特殊字符，只保留字母、数字、中文、连字符、下划线
    safe_name = re.sub(r'[^\w\u4e00-\u9fff-]', '_', experiment_name).strip('_')
    # 避免名称过长
    safe_name = safe_name[:50] if len(safe_name) > 50 else safe_name

    base_dir = get_experiment_root_dir() / f"{exp_id}_{safe_name}"

    if path_type == DataPathType.base:
        return base_dir
    elif path_type == DataPathType.weekly:
        return base_dir / "1.WeeklyData"
    elif path_type == DataPathType.model:
        return base_dir / "2.ModelData"
    elif path_type == DataPathType.backtest:
        return base_dir / "3.BackTest"
    elif path_type == DataPathType.realtime:
        return base_dir / "4.RealTime"

    else:
        raise ValueError(f"未知的路径类型: {path_type}")
    
def get_relative_path(absolute_path: Path) -> str:
    """返回相对于数据根目录的相对路径字符串，用于数据库存储"""
    root = get_root_data_dir().resolve()
    path = absolute_path.resolve()
    try:
        return str(path.relative_to(root))
    except ValueError:
        raise ValueError(f"路径 {path} 不在数据根目录 {root} 下，无法转换为相对路径")


# def get_weekly_data_dir(path_type: DataPathType = DataPathType.base):
#     """
#     获取周频数据目录.
#     - base: settings.DATA_DIR/3.WeeklyData/
#     - log : settings.DATA_DIR /3.WeeklyData/log/YYYY-MM-DD/
#     - last: settings.DATA_DIR /3.WeeklyData/last/
    
#     """
#     base_dir = _ensure_absolute(settings.DATA_DIR).resolve() / "3.WeeklyData"
#     if path_type == DataPathType.base:
#         return base_dir
#     elif path_type == DataPathType.log:
#         today_str = datetime.datetime.today().strftime('%Y-%m-%d')
#         return base_dir / "log" / today_str
#     elif path_type == DataPathType.last:
#         return base_dir / "last"
#     else:
#         raise ValueError(f"未知的路径类型: {path_type}")

# def get_model_data_dir(path_type: DataPathType = DataPathType.base):
#     """
#     获取模型数据目录
#     - base: settings.DATA_DIR/4.WeeklyData/
#     - log : settings.DATA_DIR /4.WeeklyData/log/YYYY-MM-DD/
#     - last: settings.DATA_DIR /4.WeeklyData/last/
#     """
#     base_dir = _ensure_absolute(settings.DATA_DIR).resolve() / "4.ModelData"
#     if path_type == DataPathType.base:
#         return base_dir
#     elif path_type == DataPathType.log:
#         today_str = datetime.datetime.today().strftime('%Y-%m-%d')
#         return base_dir / "log" / today_str
#     elif path_type == DataPathType.last:
#         return base_dir / "last"
#     else:
#         raise ValueError(f"未知的路径类型: {path_type}")

def safe_to_csv(df: pd.DataFrame, filepath, **kwargs):
    """
    安全地将 DataFrame 保存为 CSV 文件，若路径中目录不存在则自动创建。
    
    参数
    ----------
    df : pd.DataFrame
        要保存的数据
    filepath : str | path
        目标 CSV 文件路径（支持相对路径或绝对路径）
    **kwargs :
        传递给 df.to_csv() 的其他参数，内部默认index=False, encoding='utf-8-sig'无需重复设置
    """
    # 设置默认值（外部可通过 kwargs 覆盖）
    kwargs.setdefault('encoding', 'utf-8-sig')
    kwargs.setdefault('index', False)

    # 创建目录
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    # 保存文件
    df.to_csv(filepath, **kwargs)

# 常见日期列名（人工维护，可随时增删）
DATE_CANDIDATES = [
    "date", "DATE", "Date",
    "日期", "净值日期", "day", "trade_date", "datetime",
    "Date", "DATE",  # 重复无妨，保留
]

def find_date_column(df: pd.DataFrame) -> str | None:
    """在 DataFrame 中查找第一个存在于候选列表的日期列，返回列名。若未找到，返回 None。"""
    for col in df.columns:
        if col in DATE_CANDIDATES:
            return col
    return 

def save_json(data: dict, filepath: Path, indent: int = 2, ensure_ascii: bool = False):
    """
    将字典保存为 JSON 文件。自动创建文件所在目录。
    - data: 待保存的字典
    - filepath: Path 对象，目标文件路径
    - indent: JSON 缩进空格数
    - ensure_ascii: 是否转义非 ASCII 字符
    """
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8-sig") as f:
        json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)

def load_json(filepath: Path) -> dict:
    """从 JSON 文件读取并返回字典"""
    with open(filepath, "r", encoding="utf-8-sig") as f:
        return json.load(f)
    

    
# ------------------------------------------------------------
# 工具函数：从分钟线提取每日14:00金价
# ------------------------------------------------------------
def get_daily_1400_price(minute_df: pd.DataFrame) -> pd.Series:
    df = minute_df.copy()
    df['date'] = df['datetime'].dt.date
    df['time'] = df['datetime'].dt.time
    target = datetime.time(14, 0)

    def pick_price(group):
        before = group[group['time'] <= target]
        if not before.empty:
            return before.iloc[-1]['close_px']
        return None

    daily = df.groupby('date').apply(pick_price, include_groups=False).dropna()
    daily.index = pd.to_datetime(daily.index)
    daily.name = 'au_1400_price'
    return daily
