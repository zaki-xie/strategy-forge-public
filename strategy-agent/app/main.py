# app/main.py
import sys
import os
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from strategy_cli.config import load_env, load_config
from strategy_cli.plugins import discover_web_plugins
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama          # 已更新为独立包
from app.agent_runner import AgentRunner

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

def main():
    print("🚀 初始化 Agent 系统...")
    load_env()
    config = load_config()
    print("✅ 配置加载完成")

    llm_config = config.get("llm", {})
    provider = llm_config.get("provider", "ollama").lower()
    model = llm_config.get("model", "modelscope.cn/Qwen/Qwen2.5-7B-Instruct-GGUF:latest")
    temperature = llm_config.get("temperature", 0.7)
    base_url = llm_config.get("base_url", "http://localhost:11434")
    num_ctx = llm_config.get("num_ctx", 8192)
    timeout = llm_config.get("timeout", 120)

    if provider == "openai":
        llm = ChatOpenAI(model=model, temperature=temperature)
    elif provider == "ollama":
        llm = ChatOllama(
            model=model,
            temperature=temperature,
            base_url=base_url,
            num_ctx=num_ctx,
            timeout=timeout,
        )
    else:
        raise ValueError(f"不支持的 provider: {provider}")

    verbose = config.get("agent", {}).get("verbose", True)
    max_iterations = config.get("agent", {}).get("max_iterations", 5)

    runner = AgentRunner(llm=llm, verbose=verbose, max_iterations=max_iterations)
    runner.initialize()

    print("🤖 Agent 已就绪，输入 'exit' 退出。")
    while True:
        user_input = input("\n你: ")
        if user_input.lower() in ("exit", "quit"):
            break
        output = runner.run(user_input)
        print(f"\n助手: {output}")

if __name__ == "__main__":
    main()