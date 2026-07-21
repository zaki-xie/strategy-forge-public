# app/agent_runner.py
import logging
from typing import List, Any
from langchain.agents import create_agent
from langchain_core.language_models import BaseLLM

from tools.web_search_tool import web_search
from tools.web_extract_tool import web_extract   # 新增导入
from strategy_cli.plugins import discover_web_plugins

logger = logging.getLogger(__name__)

class AgentRunner:
    def __init__(
        self,
        llm: BaseLLM,
        tools: List[Any] = None,
        verbose: bool = True,
        max_iterations: int = 2
    ):
        self.llm = llm
        # 默认包含搜索和提取两个工具
        self.tools = tools or [web_search, web_extract]
        self.verbose = verbose
        self.max_iterations = max_iterations
        self._agent = None

    def initialize(self) -> None:
        """创建 Agent 实例并缓存"""
        discover_web_plugins()

        logger.info("正在测试 LLM 连接...")
        try:
            test_response = self.llm.invoke("你好，请回复'连接成功'")
            logger.info(f"LLM 测试回复: {test_response.content}")
        except Exception as e:
            logger.error(f"LLM 连接测试失败: {e}")
            raise RuntimeError(f"无法连接 LLM: {e}")

        # 更新系统提示词，让模型知道可以使用 web_extract
        system_prompt = """你是一个专业的助手，可以搜索并提取网页内容。

        **可用工具：**
        1. `web_search`：搜索互联网获取相关链接和摘要。
        2. `web_extract`：从指定的 URL 提取完整正文内容（Markdown 格式）。

        **使用规则：**
        - 当用户询问实时信息或新闻时，**必须**先使用 `web_search` 获取相关链接。
        - 如果需要阅读某个链接的详细内容（如文章全文），使用 `web_extract` 提取该页面的内容。
        - 可以组合使用：先搜索，再提取第一条或用户指定的链接。
        """
        self._agent = create_agent(
            model=self.llm,
            tools=self.tools,
            system_prompt=system_prompt,
        )
        logger.info("Agent 初始化完成")

    def run(self, user_input: str) -> str:
        if self._agent is None:
            raise RuntimeError("Agent 尚未初始化，请先调用 initialize()")
        try:
            response = self._agent.invoke(
                {"messages": [{"role": "user", "content": user_input}]}
            )
            return response["messages"][-1].content
        except Exception as e:
            logger.error(f"Agent 执行出错: {e}")
            return f"⚠️ 错误: {e}"