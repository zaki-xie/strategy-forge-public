from langchain_openai import ChatOpenAI

# 1. 初始化 Qwen 模型
# 默认连接本地 http://localhost:11434
llm = ChatOpenAI(
    model="models--deepseek-ai--DeepSeek-R1-Distill-Qwen-7B",                # 任意名称，服务端会使用实际模型
    openai_api_key="0",                   # 本地服务不校验，填任意值
    openai_api_base="http://localhost:8821/v1",  # 替换为你的服务器地址和端口
    temperature=0.2,                      # 较低的温度使输出更稳定
    timeout=60,           # 等待 60 秒
    max_retries=0,        # 不重试，避免累积等待
    streaming=True,  # 开启流式传输
)
# 2. 交互式对话循环
print("===== 流式交互终端 =====")
print("输入 'exit' 退出。\n")

while True:
    user_input = input("你: ").strip()
    if user_input.lower() in ("exit", "quit", "q"):
        break
    if not user_input:
        continue

    try:
        print("模型: \r\n", end="", flush=True)
        # 逐块接收并打印
        for chunk in llm.stream(user_input):
            print(chunk.content, end="", flush=True)
        print("\n")  # 换行
    except Exception as e:
        print(f"\n出错了: {e}\n")