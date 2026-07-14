import json
from typing import AsyncGenerator, Optional, Dict, Any
from openai import AsyncOpenAI
from app.core.config import settings
from app.utils.exceptions import BusinessError

# 模型配置：可后续从数据库或配置文件读取
MODEL_CONFIGS = {
    "deepseek": {
        "type": "cloud",
        "api_key": settings.DEEPSEEK_API_KEY,
        "base_url": settings.DEEPSEEK_BASE_URL,
        "model_name": settings.DEEPSEEK_MODEL,
    },
    "qwen": {
        "type": "cloud",
        "api_key": settings.QWEN_API_KEY,
        "base_url": settings.QWEN_BASE_URL,
        "model_name": settings.QWEN_MODEL,
    },
    "ollama": {
        "type": "local",
        "api_key": settings.OLLAMA_API_KEY,             # Ollama 不验证，任意字符串
        "base_url": settings.OLLAMA_BASE_URL,
        "model_name": settings.OLLAMA_MODEL,
    },
}

# 必须检查的字段
REQUIRED_FIELDS = {"api_key", "base_url", "model_name"}

def get_model_config(model: str) -> dict:
    """获取模型配置，并进行完整性校验"""
    if model not in MODEL_CONFIGS:
        raise BusinessError(f"不支持的模型: {model}，可用模型: {list(MODEL_CONFIGS.keys())}")
    
    config = MODEL_CONFIGS[model]
    missing = [field for field in REQUIRED_FIELDS if not config.get(field)]
    if missing:
        raise BusinessError(f"模型 {model} 配置不完整，缺少字段: {missing}，请检查配置文件")
    
    return config

async def chat_stream(
    model: str,
    message: str,
    system_prompt: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """流式对话，逐块返回文本增量"""
    config = get_model_config(model)
    client = AsyncOpenAI(
        api_key=config["api_key"],
        base_url=config["base_url"],
    )
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": message})

    try:
        stream = await client.chat.completions.create(
            model=config["model_name"],
            messages=messages,
            stream=True,
            timeout=120,
        )
        # stream 是 AsyncOpenAI 客户端 chat.completions.create 返回的异步可迭代对象。
        # 它的类型为 AsyncStream[ChatCompletionChunk]，即异步的 ChatCompletionChunk 流。
        # 每个 chunk 是服务端通过 SSE（Server-Sent Events）推送的一个 JSON 片段，
        # 在 SDK 内部已经被解析为 ChatCompletionChunk 对象。
        # 这个对象包含一个 choices 列表，每个 choice 包含一个 delta 对象，
        # delta 中的 content 字段是本次增量文本（可能为空字符串或 None）。
        async for chunk in stream:
            # 检查 chunk 中是否有 choices，并且第一个 choice 的 delta 中有 content 文本
            if chunk.choices and chunk.choices[0].delta.content:
                # 如果存在增量文本，就通过生成器返回（yield），让上层可以逐字获取回复
                yield chunk.choices[0].delta.content
    except Exception as e:
        raise BusinessError(f"聊天服务异常: {str(e)}")

async def chat_non_stream(
    model: str,
    message: str,
    system_prompt: Optional[str] = None,
) -> str:
    """非流式对话，返回完整回答"""
    config = get_model_config(model)
    client = AsyncOpenAI(
        api_key=config["api_key"],
        base_url=config["base_url"],
    )
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": message})

    try:
        response = await client.chat.completions.create(
            model=config["model_name"],
            messages=messages,
            stream=False,
            timeout=120,
        )
        if response.choices:
            return response.choices[0].message.content or ""
        return ""
    except Exception as e:
        raise BusinessError(f"聊天服务异常: {str(e)}")