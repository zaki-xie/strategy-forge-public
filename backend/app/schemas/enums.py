from enum import Enum

class DataDirType(str, Enum):
    """数据目录类型，用于选择要扫描的数据集"""
    original = "original"       # 原始数据 (1.OriginalData)
    processed = "processed"     # 预处理数据 (2.ProcessData)
    experiment = "experiment"   # 实验目录(3.experiment)
    # weekly = "weekly"           # 周频聚合数据 (3.WeeklyData)
    # model = "model"             # 模型数据(4.ModelData)

class SortOrder(str, Enum):
    off = "off"
    asc = "asc"
    desc = "desc"

class DataPathType(str, Enum):
    """
    数据目录类型
    - base:基础目录
    - weekly: base/1.WeeklyData
    - model: base/2.ModelData

    """
    base = "base"
    weekly = "weekly"
    model = "model"
    backtest = "backtest"
    realtime = "realtime"

class ExperimentStatus(str, Enum):
    WEEKLY_AGGREGATOR = "weekly_aggregator"
    SPLITTED = "splitted"
    TRAINED = "trained"
    BACKTESTED = "backtested"
    REALTIMED = "realtimed"