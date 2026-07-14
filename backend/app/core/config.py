# app/core/config.py
import os
from pydantic_settings import BaseSettings
from pathlib import Path
from app.core.log_handlers import DateBasedFileHandler

# ------------------------------------------------------------
# 目录常量
# ------------------------------------------------------------
# 获取 config.py 所在目录，并向上两级到达 backend/ 根
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/app/core -> backend

# 日志文件存储目录
LOG_DIR = BASE_DIR / "logs"
os.makedirs(LOG_DIR, exist_ok=True)   # 确保日志目录存在

# ------------------------------------------------------------
# 环境选择器（决定加载 .env.dev 还是 .env.prod）
# ------------------------------------------------------------
class EnvChooser(BaseSettings):
    """仅用于读取 APP_ENV 环境变量，确定当前环境"""
    APP_ENV: str = "dev"      # 默认 dev
    class Config:
        env_file = BASE_DIR / ".env",   # 从项目根目录的 .env 读取 APP_ENV
        env_file_encoding = "utf-8"
        extra = "ignore"    # 忽略其他未定义的字段

_current_env = EnvChooser().APP_ENV # 例如 "dev" 或 "prod"

# ------------------------------------------------------------
# 应用配置（根据环境加载对应的 .env.* 文件）
# ------------------------------------------------------------
class Settings(BaseSettings):
    APP_NAME: str = "Strategy-Forge"
    DEBUG: bool = False
    GOLD_API_KEY: str = ""               # GoldAPI 密钥
    FRED_API_KEY: str = ""
    HTTP_PROXY: str | None = None          # HTTP 代理（用于境外数据源）
    HTTPS_PROXY: str | None = None
    DATA_DIR: Path = BASE_DIR / "data"   # 新增：数据存放目录，默认在 /data/

    # ========== 大模型对话配置 ==========
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = ""
    DEEPSEEK_MODEL: str = ""

    QWEN_API_KEY: str = ""
    QWEN_BASE_URL: str = ""
    QWEN_MODEL: str = ""

    OLLAMA_API_KEY: str = "ollama"
    OLLAMA_BASE_URL: str = ""
    OLLAMA_MODEL: str = ""
    

    class Config:
        env_file = BASE_DIR / f".env.{_current_env}"    # 动态加载对应环境文件
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()
os.makedirs(settings.DATA_DIR, exist_ok=True)  # 确保数据目录存在
# ------------------------------------------------------------
# 日志配置字典（供 logging.config.dictConfig 使用）
# ------------------------------------------------------------
LOGGING_CONFIG = {
    "version": 1,                               # 配置格式版本，固定为 1
    "disable_existing_loggers": False,          # 是否禁用已存在的 logger（False 表示保留）
    
    # 1、 格式化器（定义日志的输出格式）
    "formatters": {
        "default": {
            # 输出格式：时间 | 日志级别 | 模块名: 消息内容
            "format": "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
            # 时间格式：年-月-日 时:分:秒
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },

     # 2、 处理器（决定日志输出到哪里）
    "handlers": {
        # 控制台处理器：输出到终端（uvicorn 运行时可见）
        "console": {
            "class": "logging.StreamHandler",   # 标准流处理器
            "formatter": "default",             # 使用上面定义的 default 格式
            #  "stream": "ext://sys.stdout",       # 输出到标准输出（可省略，默认 stderr？通常 stdout）
        },

        # 文件处理器：输出到日志文件，每天午夜自动分割
        "file": {
            "class": "app.core.log_handlers.DateBasedFileHandler",   # 按时间轮转的文件处理器
            "filename": str(LOG_DIR / "app.log"),                   # 日志文件路径
            #"when": "midnight",                  # 每天午夜滚动
            "backup_days": 30,                   # 只保留最近 30 个日志文件
            "formatter": "default",              # 使用 default 格式
            "encoding": "utf-8",
        },
    },

    # 3️、 根 logger（所有模块的默认 logger）
    "root": {
        "level": "INFO",                    # 记录 INFO 及以上级别的日志（DEBUG 级别被忽略）
        "handlers": ["console", "file"],    # 同时使用控制台和文件两个处理器
    },

    # # 4️、其他可选的特定 logger 配置（如果需要某个库的日志级别不同，可以在此调整）
    # # 例如：让 urllib3 只记录 WARNING 级别，减少噪声
    # "loggers": {
    #     "urllib3": {
    #         "level": "WARNING",
    #         "handlers": ["console", "file"],
    #         "propagate": False,             # 不向根 logger 传播
    #     },
    # },
}
# print("HTTP_PROXY:", settings.HTTP_PROXY)
# print("HTTPS_PROXY:", settings.HTTPS_PROXY)