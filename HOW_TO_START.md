# 快速启动指南 (How to Start)

## 1. 前置环境
- [Node.js](https://nodejs.org/zh-cn) ≥20.19（推荐 24.16.0）
- [Miniconda](https://www.anaconda.com/docs/getting-started/installation) 或 [Anaconda](https://www.anaconda.com/download)（用于 Python 虚拟环境）,两者区别可参考文章[Anaconda Distribution vs. Miniconda](https://www.anaconda.com/docs/getting-started/concepts/anaconda-or-miniconda)

## 2.拉取项目代码
```bash
git clone https://github.com/zaki-xie/strategy-forge-public.git
```

## 3. 获取 API 密钥
| 数据源 | 注册地址 | 获取密钥/Token |
|--------|----------|----------------|
| GoldAPI | https://gold-api.com | 注册后获得 API Key 免费版即可 |
| FRED API (DGS10) | https://fredaccount.stlouisfed.org/apikeys | 免费版即可 |

## 4. 配置环境变量
1. 复制模板文件：

使用如下指令从example中拷贝环境变量文件
```bash
cp .env.dev.example .env.dev
cp .env.prod.example .env.prod
```

2. 确认.env环境

使用.env文件切换开发环境或生产环境。

默认情况下.env文件中内容为dev生产环境，对应调用.env.dev中环境变量，若将其值修改为prod则会调用.env.prod中环境变量。
```bash
APP_ENV=dev
```

3. 填写环境变量

修改.env.dev和.env.prod对应内容为步骤3中获取到的API KEY

```bash
# GOLD_API_KEY通过https://gold-api.com/dashboard/api-keys注册账号获取，免费的API即可
GOLD_API_KEY = "YOUR_GOLD_API_KEY_HERE"
# FRED_API_KEY通过https://fredaccount.stlouisfed.org/apikeys注册账号获取，同样的免费API即可
FRED_API_KEY = "YOUR_FRED_API_KEY_HERE"
```

修改数据文件存储路径为你期望的路径,若需要存储在backend/data下可以修改为:
```bash
DATA_DIR=./data
```

其余的QWen、DeepSeek、Ollama等变量为AI chat模块相关功能，正在开发中，与策略核心功能无关，暂时无需配置
```bash
# 下面为AI相关模块配置，相关功能还在测试中，暂时无需配置
# 不配置相关内容仅会导致前端的chat通话无法使用（一个测试中的简单对话）不影响项目核心策略功能

# 从如下地址获取KEY 和 URL
#  https://api-docs.deepseek.com/zh-cn/
DEEPSEEK_API_KEY = YOUR_API
DEEPSEEK_BASE_URL = https://api.deepseek.com # 目前仅支持OpenAI格式
DEEPSEEK_MODEL = deepseek-v4-flash # deepseek-v4-flash/deepseek-v4-pro 参考 https://api-docs.deepseek.com/zh-cn/

# 从如下地址获取KEY 和 URL
# https://bailian.console.aliyun.com/cn-beijing/?tab=model&source_channel=hy_qwen#/api-key
QWEN_API_KEY = YOUR_API
QWEN_BASE_URL = https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1   
QWEN_MODEL = qwen3.7-plus # 参考阿里云百炼模型广场以及您的API配置的支持的模型类型https://bailian.console.aliyun.com/cn-beijing/?tab=model&source_channel=hy_qwen#/model-market/all

OLLAMA_API_KEY = 'ollama' # required but ignored
OLLAMA_API_URL =   # Ollama 的 OpenAI 兼容端点
OLLAMA_MODEL =
```

4. 让后端跑起来
```bash
# 创建并激活虚拟环境（推荐 Python 3.13.5）
conda create -n strategy-env python=3.13.5
conda activate strategy-env

# 安装依赖（若重装环境可加 --force-reinstall 确保版本匹配）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 启动服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
项目启动后可以查看后端的API文档页面

API 文档：`http://localhost:8000/docs`

5. 让前端跑起来

```bash
cd frontend

# npm install速度太慢可以考虑通过换源来加速（可选）
npm config set registry https://registry.npmmirror.com
# 安装相关依赖
npm install
# 以dev开发模式启动项目
npm run dev
```
启动后默认通过如下地址访问：

访问:`http://localhost:5173`

6. 开始拉取数据和回测学习吧！


### 🔒 开源版本说明
如果您访问的是本项目的 **开源版本（strategy-forge-public）**，请注意：
- 已移除涉及敏感信息的爬虫代码（`backend/app/services/wallstreetcn_kline_utils.py`），该模块用于获取上海黄金交易所 **AU99.99 分钟级K线** 数据。
- 需要您自行编写数据获取代码，并替换 `backend/app/api/routes/data_collector.py` 中 `trigger_update_kline` 接口调用的服务。
- 获取到的数据应存放于环境变量 `DATA_DIR` 下的 `1.OriginalData` 目录，文件名为 `AU9999_SGE_10year_5min.csv`。
- **参考数据格式**（CSV 表头与示例）：

| tick_at | datetime | open_px | high_px | low_px | close_px |
|--------|----------------------|--------|--------|-------|----------|
| 1539368700 | 2018-10-13 02:25:00 | 271.86 | 271.86 | 271.86 | 271.86 |

请确保您的数据源能提供类似结构的5分钟级数据，否则后续周频聚合将无法正常运行。
