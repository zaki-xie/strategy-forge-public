# talk_to_ollama_qwen.py
from langchain_ollama import ChatOllama

# 1. 初始化 Qwen 模型
# 默认连接本地 http://localhost:11434
llm = ChatOllama(
    model="modelscope.cn/Qwen/Qwen2.5-7B-Instruct-GGUF:latest",  # 替换为你在 Ollama 中看到的实际模型名
    temperature=0.2,      # 较低的温度使输出更稳定、更聚焦
)
# 2. 交互式对话循环
print("===== Qwen 2.5 交互终端 =====")
print("输入你的问题，按 Enter 发送。输入 'exit' 或 'quit' 退出。\n")

while True:
    # 获取用户输入
    user_input = input("你: ").strip()
    
    # 检查退出条件
    if user_input.lower() in ("exit", "quit", "q"):
        print("对话结束，再见！")
        break
    
    # 如果用户直接按 Enter 则跳过
    if not user_input:
        continue
    
    # 调用模型并打印回答
    try:
        response = llm.invoke(user_input)
        print(f"QWen: {response.content}\n")
    except Exception as e:
        print(f"出错了: {e}\n")