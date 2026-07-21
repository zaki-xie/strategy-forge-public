# agent服务
计划ing搭建的获取黄金相关基本面数据、采集黄金新闻、论文数据等并提供分析研报的agent。

## 框架
1. langchain提供agent配套架构；
2. Ollama提供本地模型部署；

## 注意事项
- agent模块和backend模块共用的一套conda环境，所以requirements.txt是相同的
- 目前agent配置相关包仅需pip install -U langchain langchain-ollama langchain-community duckduckgo-search ddgs

## 后续更新项目包
```bash
pip freeze > requirements.txt
```

## 服务端指令
用于llamafactory+huggingface环境启动模型参考指令
```bash
CUDA_VISIBLE_DEVICES=1 API_PORT=8821 llamafactory-cli api     --model_name_or_path /home/xiezhongjun/hugging-face/hub/models--deepseek-ai--DeepSeek-R1-Distill-Qwen-7B/snapshots/916b56a44061fd5cd7d6a8fb632557ed4f724f60     --template deepseekr1     --infer_backend huggingface
```


## 暂定架构

strategy-agent/
├── agent/                      # 核心 Agent 组件
│   ├── __init__.py
│   ├── web_search_provider.py
│   ├── web_search_registry.py
│   └── ...
├── strategy_cli/               # CLI 与基础设施
│   ├── __init__.py
│   ├── config.py               # 配置加载、环境变量
│   ├── plugins.py              # 插件加载器
│   └── ...
├── plugins/                    # 可插拔后端
│   └── web/
│       └── ddgs/
│           ├── __init__.py
│           ├── provider.py
│           └── plugin.yaml
├── tools/                      # LangChain 工具封装
│   ├── __init__.py
│   └── web_search_tool.py
├── app/                        # 应用入口与核心逻辑
│   ├── __init__.py
│   ├── main.py                 # 主入口（CLI 交互）
│   └── agent_runner.py         # Agent 运行循环
├── config.yaml                 # 配置文件
├── .env                        # 环境变量（不提交）
├── requirements.txt
└── README.md