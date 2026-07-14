# app/services/experiment_db.py
import sqlite3
import json
import os
import logging
from pathlib import Path
from datetime import datetime
from app.core.config import settings


logger = logging.getLogger(__name__)

class ExperimentRepository:
    """实验记录数据库操作类"""

    def __init__(self, db_path: Path = None):
        """
        初始化仓库，默认使用 settings.DATA_DIR / "99.ExperimentDB" / "experiments.db"
        """
        if db_path is None:
            db_path = settings.DATA_DIR / "99.ExperimentDB" / "experiments.db"
        self.db_path = db_path
        self._ensure_dir()
        self._initialized = False      # 标记表是否已创建
        
        # 若用--reload加载项目会导致加载两次python模块
        # 因此初始化时先不建表，在_ensure_initialized中执行创建
        #self._init_table()          # 自动建表

    def _ensure_dir(self):
        # .parent返回文件所在的文件夹目录
        # parents=True递归创建所有确实目录
        # 目录若已经存在，不报错，静默执行
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _ensure_initialized(self):
        """懒初始化：第一次使用时才创建表"""
        #self._ensure_columns()          # 数据库新增字段更新
        if not self._initialized:
            self._init_table()
            self._initialized = True

    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接（自动设置 row_factory 和 WAL 模式）"""
        conn = sqlite3.connect(str(self.db_path))
        # 设置连接的行工厂为 sqlite3.Row
        # 使查询结果可通过列名访问
        # 默认情况下，查询返回的是元组，只能通过索引访问列值（如 row[0]）
        # 改变后：每一行是一个 Row 对象，支持通过列名访问（如 row["column_name"]），也支持索引访问和字典方法
        conn.row_factory = sqlite3.Row
        # 将数据库的日志模式设置为 WAL（Write-Ahead Logging）
        # 默认是 DELETE，每次事务提交后删除日志文件
        # WAL 模式优点：
        # 1、读操作和写操作可以并发进行（写不阻塞读，读不阻塞写）
        # 2、性能更好，特别是在多线程或多进程同时读写时
        # 注：此设置会持久化到数据库文件，后续连接无需重复执行（除非手动改回）
        conn.execute("PRAGMA journal_mode=WAL")
        # 启用外键约束检查
        # SQLite 默认不检查外键约束（为了兼容旧版）
        # 当执行 INSERT、UPDATE、DELETE 时，会验证外键引用完整性，违反约束的操作会失败
        #conn.execute("PRAGMA foreign_keys=ON")
        return conn
    
    def _init_table(self):
        """创建实验表（如果不存在）"""
        with self._get_conn() as conn:
            # 1. 检查表是否已经存在
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='experiments'"
            )
            table_exists = cursor.fetchone() is not None

            # 2.尝试创建库表
            # 若数据表不存在则创建
            conn.execute("""
                CREATE TABLE IF NOT EXISTS experiments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    experiment_name TEXT NOT NULL,
                    status TEXT,

                    -- ===================== 周频聚合阶段 =====================
                    weekly_dir TEXT,                      -- 周频数据输出路径(相对路径)
                        
                    -- ===================== 数据分割阶段 =====================
                    split_dir TEXT,                          -- 数据分割输出路径(相对路径)
                    split_ratio REAL DEFAULT 0.7,            -- 训练集占比
                    split_factor_cols TEXT,                  -- 因子列名列表（JSON 字符串）
                    split_y_col TEXT,                        -- 目标变量列名
                    split_train_samples INTEGER,             -- 训练集样本数
                    split_test_samples INTEGER,              -- 测试集样本数
                    split_train_date_start TEXT,             -- 训练集起始日期
                    split_train_date_end TEXT,               -- 训练集结束日期
                    split_test_date_start TEXT,              -- 测试集起始日期
                    split_test_date_end TEXT,                -- 测试集结束日期
                    split_cutoff_date TEXT,                   -- 锁定分割日期（训练集结束日期），空表示未锁定,用于增量更新

                    -- ===================== 模型训练阶段 =====================
                    train_dir TEXT,                          -- 模型训练输出路径(相对路径)
                    train_model_dir TEXT,                    -- 增量训练时存放最新模型文件的路径（相对路径）
                    train_ols_window INTEGER DEFAULT 252,    -- OLS 滚动窗口大小（周数）
                    train_zscore_window INTEGER DEFAULT 52,  -- Z‑Score 计算窗口大小（周数）
                    train_buy_threshold REAL DEFAULT 0.5,    -- 买入信号阈值
                    train_sell_threshold REAL DEFAULT -0.5,  -- 卖出信号阈值
                    train_ols_train_samples INTEGER,         -- 实际训练集样本数（训练时记录）
                    train_ols_test_samples INTEGER,          -- 实际测试集样本数（训练时记录）

                    -- ===================== 回测评估阶段 =====================
                    backtest_dir TEXT,                       -- 回测输出路径(相对路径)
                    backtest_performance_json TEXT,          -- 回测绩效指标（JSON 字符串）
                    backtest_trade_signals TEXT,             -- 买卖点详情（JSON 字符串）
                    backtest_latest_snapshot TEXT,           -- 最后仓位快照（JSON 字符串)
                    backtest_buy_count INTEGER,              -- 买入次数
                    backtest_sell_count INTEGER,             -- 卖出次数
                    backtest_avg_hold_days REAL,             -- 平均持仓天数
                    
                    -- ===================== 实盘模拟阶段 =====================
                    realtime_dir TEXT,                       -- 实盘输出路径(相对路径)
                    realtime_performance_json TEXT,          -- 实盘绩效指标（JSON）
                    realtime_trade_stats_json TEXT,          -- 交易统计（JSON）
                    realtime_max_drawdown_json TEXT,         -- 最大回撤区间（JSON）
                    realtime_current_account_json TEXT,      -- 当前账户快照（JSON）
                    realtime_recent_trades_json TEXT,         -- 最近5笔交易（JSON）

                    -- ===================== 通用信息 =====================
                    output_dir TEXT,                         -- 实验输出目录
                    created_at TEXT DEFAULT (datetime('now','localtime')),
                    updated_at TEXT DEFAULT (datetime('now','localtime')),
                    notes TEXT                               -- 备注信息
                )
            """)

             # 3. 根据之前的状态输出日志
            if not table_exists:
                logger.info("✅ 已创建新的实验表: %s", self.db_path)
            else:
                logger.info("📁 实验表已存在，跳过创建: %s", self.db_path)

    def create(self, experiment_name: str, **kwargs) -> int:
        """
        创建一条实验记录，返回实验ID。
        可接受额外关键字参数：status, split_weekly_source, split_ratio, split_factor_cols,
        split_y_col, split_train_samples, split_test_samples, ..., train_ols_window, ...,
        backtest_performance_json, output_dir, notes 等
        """
        fields = ['experiment_name']
        values = [experiment_name]
        allowed_keys = [
            'status', 'weekly_dir',
            'split_dir', 'split_ratio', 'split_factor_cols', 'split_y_col',
            'split_train_samples', 'split_test_samples', 'split_train_date_start',
            'split_train_date_end', 'split_test_date_start', 'split_test_date_end','split_cutoff_date',
            'train_dir', 'train_model_dir', 'train_ols_window', 'train_zscore_window', 'train_buy_threshold',
            'train_sell_threshold', 'train_ols_train_samples', 'train_ols_test_samples',
            'backtest_dir', 'backtest_performance_json', 'backtest_trade_signals',
            'backtest_latest_snapshot', 'backtest_buy_count', 'backtest_sell_count', 'backtest_avg_hold_days',
            # 新增实盘列
            'realtime_dir', 'realtime_performance_json', 'realtime_trade_stats_json', 'realtime_max_drawdown_json',
            'realtime_current_account_json', 'realtime_recent_trades_json',
            'output_dir', 'notes'
        ]
        for key in allowed_keys:
            if key in kwargs:
                val = kwargs[key]
                # 自动序列化所有 dict/list 类型的值
                if isinstance(val, (dict, list)):
                    val = json.dumps(val, ensure_ascii=False, default=str)
                fields.append(key)
                values.append(val)

        # 生成例如 fields = ['name', 'age', 'score']，这个推导式会生成 '?', '?', '?'
        placeholders = ', '.join(['?' for _ in fields])
        # 直接将 fields 列表中的字符串用 ', ' 连接起来
        # 例如 fields = ['name', 'age', 'score'] → "name, age, score"
        fields_str = ', '.join(fields)

        with self._get_conn() as conn:
            cursor = conn.execute(
                f"INSERT INTO experiments ({fields_str}) VALUES ({placeholders})",
                values
            )
            conn.commit()
            exp_id = cursor.lastrowid # 获取刚插入行的主键值
            logger.info("创建实验 #%d: %s", exp_id, experiment_name)
            return exp_id
        
    def update(self, exp_id: int, **kwargs):
        """
        更新实验记录,可传入任意字段名（需与表列名匹配）.
        特殊处理：split_factor_cols(list) → JSON字符串；backtest_performance_json(dict) → JSON字符串。
        """
        if not kwargs:
            return
        
        # 处理 JSON 序列化字段
        # 自动序列化 JSON 字段
        for key, val in kwargs.items():
            if isinstance(val, (dict, list)):
                kwargs[key] = json.dumps(val, ensure_ascii=False, default=str)

        # 生成例如: 'split_ratio = ?, buy_threshold = ?, notes = ?'
        set_clause = ', '.join([f"{k} = ?" for k in kwargs.keys()])
        values = list(kwargs.values())
        values.append(exp_id)

        with self._get_conn() as conn:
            conn.execute(
                f"UPDATE experiments SET {set_clause}, updated_at = datetime('now','localtime') WHERE id = ?",
                values
            )
            conn.commit()
            logger.info("更新实验 #%d: %s", exp_id, kwargs)

    def get(self, exp_id: int) -> dict | None:
        """获取单个实验记录，返回字典（JSON 字段自动解析）"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM experiments WHERE id = ?", (exp_id,)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_dict(row)
        
    def list(self, limit: int = 50) -> list[dict]:
        """列出最近实验记录（按创建时间倒序）"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM experiments ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [self._row_to_dict(row) for row in rows]

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        """将 sqlite3.Row 转换为普通字典，并尝试解析 JSON 字段"""
        d = dict(row)
        # 尝试自动反序列化所有看起来像 JSON 的字符串字段
        for key, val in d.items():
            if isinstance(val, str) and (val.startswith('{') or val.startswith('[')):
                try:
                    d[key] = json.loads(val)
                except json.JSONDecodeError:
                    pass
        return d
    def delete(self, exp_id: int) -> bool:
        """
        删除指定实验的记录。返回 True 表示删除成功，False 表示记录不存在。
        """
        with self._get_conn() as conn:
            cursor = conn.execute(
                "DELETE FROM experiments WHERE id = ?", (exp_id,)
            )
            conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info("删除实验 #%d", exp_id)
            else:
                logger.warning("尝试删除不存在的实验 #%d", exp_id)
            return deleted
        
    def _ensure_columns(self):
        new_columns = {
            'train_model_dir': 'TEXT',
            'split_cutoff_date': 'TEXT',
            # 若有其他新增列也在此定义
        }
        with self._get_conn() as conn:
            existing = [row[1] for row in conn.execute("PRAGMA table_info(experiments)")]
            for col, col_type in new_columns.items():
                if col not in existing:
                    conn.execute(f"ALTER TABLE experiments ADD COLUMN {col} {col_type}")
                    logger.info("数据库已添加列: %s", col)

# 全局单例实例，方便直接调用
experiment_repo = ExperimentRepository()