#  app/schemas/common.py
# 模块定义了一个通用的 API 响应模型，
# 使用 Pydantic 的 BaseModel 来创建一个数据模型类 ApiResponse。
from pydantic import BaseModel
from typing import Any, Optional

class BusinessCode:
    SUCCESS = 0                     # 成功
    PARAM_ERROR = 1001              # 参数错误
    FILE_NOT_FOUND = 1002           # 文件不存在
    DATA_SOURCE_ERROR = 1003        # 数据源请求失败
    PROCESSING_ERROR = 2001         # 处理过程异常
    UNKNOWN_ERROR = 9999            # 未知错误

class ApiResponse(BaseModel):
    code: int            # 业务状态码（0 表示成功，非 0 表示异常）
    message: str         # 提示信息（给用户看的）
    data: Any = None     # 实际数据（可选）

    class Config:
        # 提供一个快速创建成功响应的静态方法（可选，方便使用）
        @staticmethod
        def success(message: str = "操作成功", data: Any = None):
            return ApiResponse(code=BusinessCode.SUCCESS, message=message, data=data)