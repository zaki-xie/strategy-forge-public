# Strategy Forge 后端

基于 FastAPI 的量化策略研究后端，负责数据采集、因子工程、模型训练、回测、实盘模拟与 WebSocket 实时通知。

---

## 环境搭建

```bash
# 创建虚拟环境（推荐 Python 3.13.5）
conda create -n strategy-env python=3.13.5

# 激活环境
conda activate strategy-env

# 安装依赖（若重装环境可加 --force-reinstall 确保版本匹配）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 启动程序

```bash
# 默认启动（localhost:8000）
uvicorn app.main:app --reload

# 指定主机和端口，带优雅关闭超时
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --timeout-graceful-shutdown 5
```

## API 文档

- Swagger UI：`http://127.0.0.1:8000/docs`
- ReDoc：`http://127.0.0.1:8000/redoc`

---
## 后续更新项目包
```bash
pip freeze > requirements.txt
```
## 项目结构

```
backend/app/
├── api/routes/               # API 路由
│   ├── data_collector.py     # 数据采集接口
│   ├── data_view.py          # 数据浏览、金价、回测/实盘数据接口
│   ├── strategy.py           # 策略流程控制接口
│   ├── experiment.py         # 实验管理接口
│   ├── ws.py                 # WebSocket 实时通知
│   └── __init__.py
├── services/                 # 核心业务逻辑
│   ├── backtest_data_service.py  # 回测数据查询
│   ├── backtest.py           # 回测模拟与绩效评估
│   ├── data_collector.py     # 各数据源更新逻辑
│   ├── data_preprocessing.py  # 数据清洗与重命名
│   ├── experiment_service.py  # 实验记录与本地实验文件删除服务
│   ├── gold_data_service.py  # 黄金价格类数据重采样数据服务（日线、周线等）
│   ├── realtime_data_service.py  # 实盘数据查询
│   ├── realtime.py           # 实盘资金模拟（FIFO＋赎回费）
│   ├── rolling_ols.py        # 滚动OLS训练与增量训练
│   ├── train_test_split.py   # 训练/测试集划分（支持锁定分割日期）
│   ├── wallstreetcn_kline_utils.py  # 华尔街见闻K线爬虫
│   ├── weekly_aggregator.py  # 周频聚合与因子计算
│   └── ws_manager.py         # WebSocket 连接管理
├── database/                 # 数据持久化
│   └── experiment_repo.py    # SQLite 实验记录 CRUD（JSON 自动序列化）
├── schemas/                  # 数据模型与枚举
│   ├── common.py             # 统一响应格式 ApiResponse
│   └── enums.py              # 数据目录、实验状态等枚举
├── core/                     # 核心配置与基础组件
│   ├── config.py             # 多环境配置管理
│   ├── exceptions.py         # 全局异常处理
│   └── log_handlers.py       # 按日日志，自动清理
└── utils/                    # 工具函数
    ├── backtest_utils.py     # 绩效评估、夏普、最大回撤计算工具
    ├── data_utils.py         # 数据路径工具、json读写工具
    ├── datetime_utils.py     # 日期工具
    ├── exception.py          # 业务异常BusinessError
    └── task_utils.py         # 后台任务封装与 WebSocket 通知
```

---

## 主要功能模块

| 模块 | 说明 |
|------|------|
| 数据采集 | 十余种数据源（AU9999、联接基金净值、国际金价、美元指数等）支持全量/增量更新 |
| 数据预处理 | 统一清洗、重命名，生成规范化 CSV |
| 周频聚合 | 按周五对齐，计算趋势、偏离度、收益率等因子 |
| 训练/测试集划分 | 按比例或锁定日期划分，支持增量更新 |
| 滚动OLS训练 | 首次全量训练或后续增量追加信号，生成预测信号和 Z-Score |
| 回测 | 生成策略净值、基准净值、买卖点，计算夏普、最大回撤、年化收益 |
| 实盘模拟 | 初始 1 万元，FIFO 卖出，含赎回费，生成账户快照与交易记录 |
| 实验管理 | SQLite 存储实验生命周期，JSON 自动序列化，支持 CRUD |
| 实时通知 | WebSocket 广播任务完成/失败，前端实时响应 |