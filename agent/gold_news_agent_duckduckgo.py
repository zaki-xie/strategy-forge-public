import os
from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langchain.agents import create_agent
from langchain_community.tools import DuckDuckGoSearchResults
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper

load_dotenv()

# ========== 1. 初始化模型 ==========
llm = ChatOllama(
    model="modelscope.cn/Qwen/Qwen2.5-7B-Instruct-GGUF:latest",
    temperature=0.2,
    num_ctx=8192,
)

# ========== 2. 创建 DuckDuckGo 搜索工具（带代理配置） ==========
# 配置 API 包装器，可指定代理和区域
api_wrapper = DuckDuckGoSearchAPIWrapper(
    region="cn",           # 中国区，尝试返回中文结果
    max_results=10,        # 期望返回结果数（但实际可能少于该值）
    # proxies 参数：支持 http/socks5 代理
    # 请将 7890 换成你代理客户端的实际端口
    #proxies="http://127.0.0.1:7890",  # 如果你的代理客户端支持 HTTP 代理
    # 如果使用 SOCKS5，可以写 "socks5://127.0.0.1:7891"
)

# 创建搜索工具
search_tool = DuckDuckGoSearchResults(
    api_wrapper=api_wrapper,
    # max_results=10,  # 也可在此处指定，但建议在 wrapper 中设置
)

# 注意：该工具的名称是 "duckduckgo_search"，描述为 "A wrapper around DuckDuckGo Search ..."

# ========== 3. 系统提示词（指明工具名称） ==========
system_prompt = """你是一个专业的黄金市场新闻分析助手。

当用户询问实时信息或新闻时，**必须**使用 `duckduckgo_search` 工具获取最新数据。

工具会返回搜索结果，包含标题、链接和摘要（通常以列表形式）。
请从工具返回的文本中提取信息，并翻译成中文后按照以下 Markdown 格式整理输出：

---
### 标题
- **链接**: [点击查看](链接地址)
- **摘要**: (从工具结果中提取)

（重复上述结构，每条新闻一个区块）
"""

# ========== 4. 创建 Agent ==========
agent = create_agent(
    model=llm,
    tools=[search_tool],   # 直接传入工具实例
    system_prompt=system_prompt,
)

# ========== 5. 交互循环 ==========
print("===== 黄金新闻采集 Agent (LangChain DuckDuckGo) =====")
print("输入 'exit' 或 'quit' 退出。\n")

while True:
    user_input = input("你: ").strip()
    if user_input.lower() in ("exit", "quit", "q"):
        print("再见！")
        break
    if not user_input:
        continue

    print("Agent: 正在搜索...")
    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": user_input}]}
        )
        final_message = result["messages"][-1]
        print(f"\n{final_message.content}\n")
    except Exception as e:
        print(f"出错了: {e}\n")