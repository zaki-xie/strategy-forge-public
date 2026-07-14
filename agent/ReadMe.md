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