from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from app.schemas.common import ApiResponse
from app.utils.exceptions import BusinessError
import logging

logger = logging.getLogger(__name__)

async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=ApiResponse(
            code=exc.status_code,
            message=exc.detail,
            data=None
        ).model_dump()
    )

async def business_error_handler(request: Request, exc: BusinessError):
    logger.warning(f"业务异常: {exc.message}")   # 只记录警告，不打印堆栈
    return JSONResponse(
        status_code=200,          # 保持前端统一响应格式
        content=ApiResponse(
            code=1,               # 业务错误码，按需修改
            message=exc.message,
            data=None
        ).model_dump()
    )