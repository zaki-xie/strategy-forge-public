import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from app.services.chat_service import chat_stream, chat_non_stream, MODEL_CONFIGS
from app.schemas.common import ApiResponse, BusinessCode
from app.utils.exceptions import BusinessError

router = APIRouter(prefix="/chat", tags=["AI对话"])

class ChatRequest(BaseModel):
    message: str
    model: str = "ollama"              # 默认使用本地 Ollama
    stream: bool = True                # 默认流式输出
    system_prompt: Optional[str] = None

@router.post("/send")
async def send_chat(request: ChatRequest):
    """发送聊天消息，支持流式和非流式"""
    if request.stream:
        async def event_generator():
            try:
                async for chunk in chat_stream(
                    model=request.model,
                    message=request.message,
                    system_prompt=request.system_prompt,
                ):
                    yield f"data: {json.dumps({'content': chunk})}\n\n"
                yield "data: [DONE]\n\n"
            except BusinessError as e:
                yield f"data: {json.dumps({'error': e.message})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': f'服务器内部错误: {str(e)}'})}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")
    else:
        try:
            answer = await chat_non_stream(
                model=request.model,
                message=request.message,
                system_prompt=request.system_prompt,
            )
            return ApiResponse(
                code=BusinessCode.SUCCESS,
                message="成功",
                data={"content": answer}
            )
        except BusinessError as e:
            return ApiResponse(code=1, message=e.message, data=None)
        except Exception as e:
            return ApiResponse(code=1, message=f"服务器内部错误: {str(e)}", data=None)

@router.get("/models")
async def list_models():
    """返回可用的模型列表"""
    models = [{"name": k, "type": v["type"]} for k, v in MODEL_CONFIGS.items()]
    return ApiResponse(code=BusinessCode.SUCCESS, message="成功", data=models)