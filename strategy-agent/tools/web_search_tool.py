# tools/web_search_tool.py
import logging

from langchain.tools import tool
from agent.web_search_registry import get_active_search_provider

logger = logging.getLogger(__name__)

@tool
def web_search(query: str, limit: int = 5) -> str:
    """
    搜索互联网获取实时信息。当用户需要最新新闻、数据或你不知道答案时使用。
    
    Args:
        query: 搜索关键词
        limit: 返回结果数量，默认5条
    """
    provider = get_active_search_provider()
    logger.info(f"provider={provider.name}")
    if provider is None:
        return "错误：没有配置可用的搜索后端，请检查 config.yaml 或插件加载。"
    
    result = provider.search(query, limit=limit)
    if result.get("success"):
        items = result["data"]["web"]
        if not items:
            return "未找到相关结果。"
        # 格式化为易读文本
        output = []
        for i, item in enumerate(items, 1):
            output.append(f"{i}. {item['title']}\n   URL: {item['url']}\n   描述: {item['description']}")
        return "\n\n".join(output)
    else:
        return f"搜索失败：{result.get('error')}"