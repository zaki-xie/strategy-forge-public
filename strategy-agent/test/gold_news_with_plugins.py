import sys
import os

import logging

# 设置日志级别为 DEBUG，让所有 logger.debug 和 logger.info 都显示
# logging.basicConfig(
#     level=logging.DEBUG,
#     format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
# )


# 将项目根目录（strategy-agent/）添加到 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# test/gold_news_with_plugins.py
from strategy_cli.plugins import discover_web_plugins
from agent.web_search_registry import get_active_search_provider,list_providers

# 1. 加载所有 Web 插件（会自动注册 DDGS）
discover_web_plugins()

from strategy_cli.config import load_config,get_config_path

print(f"path={get_config_path()}")

cfg = load_config()
# print("Loaded config:", cfg)
print("web section:", cfg.get("web"))
print("Registered providers:", [p.name for p in list_providers()])

# 2. 获取当前激活的搜索提供者（根据 config.yaml 或自动选择）
provider = get_active_search_provider()
if provider:
    print(f"Using provider: {provider.name}")
    result = provider.search("黄金价格 2026", limit=3)
    print(result)
else:
    print("No search provider available")