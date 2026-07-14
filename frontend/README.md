# Strategy Forge 前端

基于 Vue 3 + TypeScript + Vite 构建的量化策略研究前端，提供交互式实验管理、回测/实盘分析、多维度图表展示与实时任务通知。

---

## 技术栈

- **框架**：Vue 3 (Composition API + `<script setup>`)
- **构建工具**：Vite
- **语言**：TypeScript
- **UI 组件库**：Element Plus
- **HTTP 客户端**：Axios（封装于 `src/api/http.ts`，统一拦截响应）
- **图表**：ECharts（原生集成，交互式缩放与提示）
- **路由**：Vue Router 4 (嵌套路由 + KeepAlive 多标签缓存)
- **实时通信**：WebSocket 多连接（分别订阅 task_completed / experiment_completed 频道），断开自动重连

---

## 项目结构

```
frontend/src/
├── api/                  # Axios 实例 + 各模块 API 函数
│   ├── dataCollector.ts  # 数据采集接口
│   ├── dataView.ts       # 数据查看、回测/实盘数据接口
│   ├── experiment.ts     # 实验管理接口
│   ├── http.ts           # 统一请求拦截与错误处理
│   ├── strategy.ts       # 策略流程控制接口
│   └── types.ts           # 通用类型
├── components/           # 公共组件
│   ├── DataFileBrowser.vue        # 数据文件浏览
│   ├── ExperimentDetailDialog.vue # 实验详情
│   └── ExperimentSelector.vue     # 实验选择器
├── composables/          # 组合式函数
│   └── useGlobalWebSocket.ts  # WebSocket 连接管理（多连接、重连）
├── layouts/              # 布局组件
│   └── MainLayout.vue    # 侧边栏 + 顶部多标签导航、KeepAlive
├── router/               # 路由配置（嵌套路由）
├── views/                # 页面视图
│   ├── BacktestAnalysis.vue  # 回测分析
│   ├── Dashboard.vue     # 仪表盘
│   ├── DataSources.vue   # 数据采集
│   ├── Experiments.vue   # 实验总览
│   ├── GoldDashboard.vue # 黄金价格走势
│   ├── RealtimeAnalysis.vue  # 实盘分析
│   └── Strategy.vue      # 策略流程控制
└── App.vue               # 根组件（WebSocket 初始化、全局通知监听）
```

---

## 安装与运行

```bash
# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

访问 `http://localhost:5173`

---

## 开发指南

- **API 请求**：所有请求通过 `src/api/http.ts` 拦截器预处理；具体接口在 `src/api/` 下的模块文件定义，Vue 组件中直接调用。
- **新增页面**：在 `src/views/` 下创建 `.vue` 文件，在 `src/router/index.ts` 的 `children` 中添加路由（`meta.title` 用于标签页标题），在 `MainLayout.vue` 的侧边栏菜单中添加 `el-menu-item`。
- **状态缓存**：支持 KeepAlive 多标签缓存，已配置 `cachedComponents` 列表；关闭标签即销毁缓存。
- **实时通知**：全局 WebSocket 连接在 `App.vue` 中初始化，所有页面共享 `latestMessage`；任务完成后自动弹窗提示，策略页面联动刷新实验列表。