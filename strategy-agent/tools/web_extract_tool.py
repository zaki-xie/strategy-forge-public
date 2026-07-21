# tools/web_extract_tool.py
import asyncio
import inspect
from langchain.tools import tool
from agent.web_search_registry import get_active_extract_provider


@tool
def web_extract(urls: list[str], format: str = "markdown", char_limit: int = None) -> str:
    """
    从指定的 URL 提取网页内容（Markdown/HTML），适合获取完整文章内容。
    当搜索结果中只包含标题和链接，需要阅读详细内容时使用。

    Args:
        urls: 要提取的 URL 列表（最多5个）
        format: 输出格式，可选 "markdown" 或 "html"，默认 markdown
        char_limit: 每页字符限制，默认由 Provider 决定（如 Firecrawl 为 15000）
    """
    provider = get_active_extract_provider()
    if provider is None:
        return "错误：没有配置可用的内容提取后端，请检查 config.yaml 或插件加载。"

    # 兼容同步/异步 extract 方法
    if inspect.iscoroutinefunction(provider.extract):
        try:
            # 在同步函数中调用异步方法，使用 asyncio.run 安全（无事件循环时）
            results = asyncio.run(provider.extract(urls, format=format, char_limit=char_limit))
        except RuntimeError:
            # 如果有正在运行的事件循环，则创建新循环运行（极少见）
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            results = loop.run_until_complete(provider.extract(urls, format=format, char_limit=char_limit))
            loop.close()
    else:
        results = provider.extract(urls, format=format, char_limit=char_limit)

    if not results:
        return "未提取到任何内容。"

    output = []
    for r in results:
        if r.get("error"):
            output.append(f"❌ {r['url']}: {r['error']}")
        else:
            title = r.get("title", "无标题")
            content = r.get("content", "")
            # 截断过长的内容（保留前 2000 字符，避免上下文爆炸）
            if len(content) > 2000:
                content = content[:2000] + "...(截断)"
            output.append(f"📄 **{title}**\nURL: {r['url']}\n\n{content}")

    return "\n\n" + ("-" * 40) + "\n\n".join(output)