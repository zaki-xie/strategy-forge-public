from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import register_routers
import logging.config
from app.core.config import LOGGING_CONFIG, settings
from contextlib import asynccontextmanager
import warnings
import asyncio
from app.utils.exceptions import BusinessError
from app.core.exceptions import http_exception_handler, business_error_handler
import signal
from app.services.ws_manager import ws_manager
from app.database.experiment_repo import experiment_repo
# 屏蔽未来警告
warnings.filterwarnings("ignore", category=FutureWarning)


# 加载日志配置
logging.config.dictConfig(LOGGING_CONFIG)


@asynccontextmanager
async def lifespan(app: FastAPI):
    experiment_repo._ensure_initialized()   # 初始化数据库表
    print("📋 API 文档：http://127.0.0.1:8000/docs")
    yield

 


logger = logging.getLogger(__name__)

app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)
# app = FastAPI(title=settings.APP_NAME)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
# 自动注册所有路由
register_routers(app)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(BusinessError, business_error_handler)

@app.get("/")
def read_root():
    return {"status": "ok"}

