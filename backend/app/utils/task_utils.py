# app/utils/task_utils.py
import asyncio
import logging
from typing import Callable
from app.services.ws_manager import ws_manager
from app.utils.exceptions import BusinessError
import inspect

logger = logging.getLogger(__name__)

async def run_with_ws_notify(
    task_name: str,
    update_func: Callable,
    *args,
    event_type: str = "task_completed",
    **kwargs
):
    """
    在后台线程中执行 update_func，完成后通过 SSE 推送通知。
    - task_name: 任务显示名称（用于日志和前端提示）
    - update_func: 同步更新函数
    - event_type: SSE 事件类型
    """
    try:
        # 将同步函数放到线程池中执行，避免阻塞事件循环
        loop = asyncio.get_running_loop()
        if inspect.iscoroutinefunction(update_func): # 判断是否为异步函数
            result = await update_func(*args, **kwargs) # 异步函数await执行
        else:
            result = await loop.run_in_executor(None, lambda: update_func(*args, **kwargs)) # 同步函数，放到线程池

        # 成功消息
        msg = {
            "message": f"{task_name} 已完成",
            "type": "success",
            "task": task_name
        }

        # 如果函数返回了 dict，则把返回值作为 data 字段，方便前端使用
        if isinstance(result, dict):
            msg["data"] = result

        await ws_manager.broadcast(event_type, msg)
        logger.info(f"通知已发送：{task_name} 完成")

    except BusinessError as e:
        # 预期的业务错误，发送明确提示
        await ws_manager.broadcast(event_type, {
            "message": f"{task_name} 失败：{e.message}",
            "type": "error",
            "task": task_name
        })
    except Exception as e:
        logger.error(f"{task_name} 执行失败: {e}")
        await ws_manager.broadcast(event_type, {
            "message": f"{task_name} 失败: {str(e)}",
            "type": "error",
            "task": task_name
        })