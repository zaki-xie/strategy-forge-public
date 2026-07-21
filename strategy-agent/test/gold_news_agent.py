import os
from typing import List
from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy  # 新增导入
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from ddgs import DDGS
import json

load_dotenv()

# ========== 1. 数据结构（增加 factor_type） ==========
class NewsItem(BaseModel):
    title: str = Field(description="新闻标题")
    summary: str = Field(description="AI 生成的事件摘要，需说明对金价的潜在影响方向（利多/利空/中性）")
    raw_snippet: str = Field(description="搜索引擎返回的原文片段")
    source_url: str = Field(description="新闻原文链接")
    factor_type: str = Field(description="基本面因子类型：货币政策/地缘政治/美元指数/央行储备/经济事件")

class NewsResponse(BaseModel):
    news_list: List[NewsItem] = Field(description="基本面新闻列表")

# ========== 2. 初始化模型 ==========
llm = ChatOllama(
    model="modelscope.cn/Qwen/Qwen2.5-7B-Instruct-GGUF:latest",
    temperature=0.2,
    num_ctx=8192,
)

# ========== 3. 搜索工具（基本面导向） ==========
@tool
def web_search(query: str, num_results: int = 5) -> str:
    """
    使用 DuckDuckGo 搜索黄金基本面相关信息。
    自动过滤价格报价类内容，优先召回事件驱动型新闻。
    """
    try:
        # 移除查询中可能导致返回报价的词汇
        base_query = query.replace("价格", "").replace("预测", "").replace("走势", "").strip()
        if not base_query:
            base_query = query

        # 构造多个搜索词，覆盖不同类型的基本面事件
        search_queries = [
            f"{base_query} 黄金 美联储",
            f"{base_query} 黄金 地缘政治",
            f"{base_query} 黄金 美元 指数",
            f"{base_query} 黄金 通胀 数据",
            f"{base_query} 黄金 央行",
        ]

        all_results = []
        seen_urls = set()
        # 最多使用4组搜索词，避免耗时过长
        for sq in search_queries[:4]:
            try:
                results = list(DDGS().text(
                    sq,
                    max_results=num_results,
                    region="cn",
                    timelimit="7d",  # 尽量获取近期新闻
                ))
                for r in results:
                    href = r.get('href', '')
                    if href in seen_urls:
                        continue
                    seen_urls.add(href)
                    all_results.append(r)
            except Exception:
                continue

        # 如果主动构造的查询没有结果，回退到原始查询
        if not all_results:
            all_results = list(DDGS().text(query, max_results=5, region="cn"))

        if not all_results:
            return f"未找到关于 '{query}' 的搜索结果。"

        # 格式化返回
        parts = []
        for idx, res in enumerate(all_results[:num_results], 1):
            title = res.get('title', '无标题')
            body = res.get('body', '无摘要')
            href = res.get('href', '#')

            title = title.replace('"', "'").replace('\\', '')
            body = body.replace('"', "'").replace('\\', '')
            href = href.replace('"', "'").replace('\\', '')

            parts.append(
                f"{idx}. 标题: {title}\n"
                f"   链接: {href}\n"
                f"   原文片段: {body}\n"
            )

        result_text = "\n".join(parts)
        result_text = result_text.replace('"', "'").replace('\\', '')
        return result_text

    except Exception as e:
        return f"搜索时发生错误: {str(e)}"


# ========== 4. 系统提示词（修改：指示模型通过工具提交结果） ==========
system_prompt = """你是一个专业的黄金市场基本面分析师。

当用户询问黄金相关信息时，**必须**使用 `web_search` 工具获取最新数据。

**信息筛选标准（非常重要）**：
你需要优先收集和整理**能够影响黄金涨跌的基本面事件**，包括但不限于：
1. **货币政策**：美联储利率决议、官员讲话、通胀数据（CPI/PPI）、非农就业
2. **地缘政治**：国际冲突、贸易制裁、大选事件
3. **美元指数**：美元走势与黄金的负相关关系
4. **央行黄金储备**：各国央行的购金/售金动向
5. **经济数据**：GDP、PMI、消费者信心指数等

**你需要明确排除的内容**：
- 单纯展示"今日金价多少一克"的报价页面
- 缺乏事件驱动逻辑的纯技术分析
- 非权威来源的散户观点

完成搜索和信息筛选后，**你必须通过调用 `submit_news` 工具来提交最终的新闻列表**。
不要直接输出文本或 JSON，直接调用工具即可，工具会自动处理返回格式。
"""

# ========== 5. 创建 Agent（使用 ToolStrategy） ==========
agent = create_agent(
    model=llm,
    tools=[web_search],
    system_prompt=system_prompt,
    response_format=ToolStrategy(
        schema=NewsResponse,
        tool_message_content="新闻列表已成功整理！"
    )
)

# ========== 6. 交互循环（简化，依赖 structured_response） ==========
print("===== 黄金基本面采集 Agent (ToolStrategy) =====")
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

        structured_output = result.get("structured_response")

        if structured_output:
            print("\n===== 基本面新闻列表 =====")
            for idx, news in enumerate(structured_output.news_list, 1):
                print(f"\n--- 新闻 {idx} ---")
                print(f"标题: {news.title}")
                print(f"因子类型: {news.factor_type}")
                print(f"AI 摘要: {news.summary}")
                print(f"原文片段: {news.raw_snippet}")
                print(f"来源: {news.source_url}")
            print("\n==========================\n")
        else:
            # 极端兜底：如果框架解析失败，打印原始消息
            final_message = result["messages"][-1]
            print(f"\n[框架解析失败，显示原始内容]\n{final_message.content}\n")

    except Exception as e:
        print(f"出错了: {e}\n")


# ===== 黄金基本面采集 Agent (ToolStrategy) =====
# 输入 'exit' 或 'quit' 退出。

# 你: 可能影响黄金涨跌的因素和趋势
# Agent: 正在搜索...

# ===== 基本面新闻列表 =====

# --- 新闻 1 ---
# 标题: 美联储降息致金价震荡 | 中国能源网
# 因子类型: 货币政策
# AI 摘要: 美联储的货币政策对黄金价格有显著影响。本次降息可能暂时不会改变黄金的上行趋势，但未来降息次数可能会减少，且美联储更多依赖实际经济数据做决策。这表明当前市场仍处于鹰派状态，对金价构成利空压力。
# 原文片段: 美联储降息致金价震荡。本次降息的影响尚未扭转黄金上行趋势。点阵图显示明年降息次数将会减半，但美联储更多依靠实际经济 数据来做决定，加之特朗普政策落地实施的时间和力度存在不确定性，当前美联储鹰派。
# 来源: https://www.cnenergynews.cn/article/4OAdlatD4w6

# --- 新闻 2 ---
# 标题: 美联储决策与黄金价格走势的关系|非农资讯网
# 因子类型: 货币政策
# AI 摘要: 美联储的货币政策是当前影响黄金价格的核心因素之一。通过分析其决策机制，可以更好地理解其对金价的影响。短期来看，美联储的政策变化会对市场情绪产生即时影响；长期而言，则会影响投资者对于未来经济前景的看法，从而间接影响金价走势。
# 原文片段: 一、美联储决策对黄金价格的影响机制二、美联储决策对黄金市场的短期影响三、美联储决策与黄金价格的长期关联
# 来源: https://www.loyoki.cn/mlcyxsj/6680.html

# --- 新闻 3 ---
# 标题: 基本面到底要怎么看？ 学精还是学杂？...from REAL0962 - Followme
# 因子类型: 地缘政治
# AI 摘要: 地缘政治事件对金价的影响不容忽视。当前主要关注点包括美国、中国、欧洲和俄罗斯的政治动态，以及俄乌冲突、中东局势等军事行动。这些因素可能导致市场避险情绪上升或下降，从而影响金价走势。
# 原文片段: 主要影响黄金的政治因素：美国，中国，欧洲，俄罗斯. 主要影响黄金的军事因素. 俄乌战场、中东局势、半岛局势.
# 来源: https://www.followme.com/c/23612273

# --- 新闻 4 ---
# 标题: 江沐洋：5.7黄金早盘策略看延续上涨，高空为主思路_汇聚热文_PC...
# 因子类型: 货币政策
# AI 摘要: 美联储继续维持高利率水平，短期内对金价构成利空压力。市场预期未来几年内不会出现降息，首次降息可能要等到2027年。这表明当前货币政策环境不利于黄金价格的上涨。
# 原文片段: 美联储的货币政策是当前影响黄金价格的核心因素之一。4月29日，美联储宣布连续第三次维持联邦基金利率目标区间于3.50%-3.75%不变，且市场对2026年内降息的预期基本消失，首次降息时点可能推迟至2027年。
# 来源: https://www.longau.com/article/2026-5-7/1778117731622.html

# --- 新闻 5 ---
# 标题: k.sina.com.cn/article_7879922977_1d5ae152106801b112.html
# 因子类型: 地缘政治
# AI 摘要: 美联储的降息预期会通过降低持有黄金的机会成本来驱动金价上涨。当前市场对降息的预期减弱，可能导致短期内金价承压，但长期来看仍可能受到避险需求的支持。
# 原文片段: 降息预期如何驱动黄金价格：三大核心机制. 利率与黄金的负相关性。美联储降息直接降低持有黄金的机会成本。
# 来源: https://k.sina.com.cn/article_7879922977_1d5ae152106801b112.html

# ==========================

# 你: exit
# 再见！