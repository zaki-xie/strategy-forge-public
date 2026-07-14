<template>
  <el-container style="height: 100vh;">
    <!-- 侧边栏（保持不变） -->
    <el-aside width="220px" style="background-color: #f5f7fa; display: flex; flex-direction: column; border-right: 1px solid #dcdfe6;">
      
      <el-header style="display: flex; align-items: center; padding: 0 20px; border-bottom: 1px solid #dcdfe6; background-color: #fff; height: 60px;">
        <el-icon :size="24" style="margin-right: 8px; color: #409EFF;">
          <Coin />
        </el-icon>
        <span style="font-size: 17px; font-weight: 600; color: #303133;">Strategy Forge</span>
      </el-header>

      <el-menu
        router
        :default-active="route.path"
        style="border-right: none; flex: 1;"
      >
        <el-menu-item index="/dashboard">
          <el-icon><Odometer /></el-icon>
          <span>仪表盘</span>
        </el-menu-item>
        <el-menu-item index="/data-collector">
          <el-icon><Download /></el-icon>
          <span>数据采集</span>
        </el-menu-item>
        <el-menu-item index="/strategy">
          <el-icon><TrendCharts /></el-icon>
          <span>策略中心</span>
        </el-menu-item>
        <el-menu-item index="/experiments">
          <el-icon><Collection /></el-icon> 
          <span>实验总览</span>
        </el-menu-item>
        <el-menu-item index="/gold-dashboard">
          <el-icon><TrendCharts /></el-icon>
          <span>黄金价格</span>
        </el-menu-item>
        <el-menu-item index="/backtest-analysis">
          <el-icon><DataAnalysis /></el-icon>
          <span>回测分析</span>
        </el-menu-item>
        <el-menu-item index="/realtime-analysis">
          <el-icon><TrendCharts /></el-icon>
          <span>实盘分析</span>
        </el-menu-item>
        <el-menu-item index="/chat">
          <el-icon><ChatDotRound /></el-icon>
          <span>量化助手</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <!-- 右侧主体 -->
    <el-container>
      <!-- 顶栏：多标签页导航 -->
      <el-header style="background: #fff; border-bottom: 1px solid #dcdfe6; padding: 0 20px; height: 60px; display: flex; align-items: center;">
        <el-tabs
          v-model="activeTab"
          type="card"
          class="header-tabs"
          @tab-remove="removeTab"
          @tab-click="handleTabClick"
        >
          <el-tab-pane
            v-for="tab in visitedRoutes"
            :key="tab.path"
            :name="tab.path"
            :closable="tab.path !== '/dashboard'"
          >
            <template #label>
              <span>{{ tab.title }}</span>
            </template>
          </el-tab-pane>
        </el-tabs>
      </el-header>

      <el-main>
        <!-- 使用 keep-alive 缓存组件状态 -->
        <router-view v-slot="{ Component }">
          <keep-alive :include="cachedComponents">
            <component :is="Component" />
          </keep-alive>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Odometer, Download, Coin, TrendCharts, Collection, DataAnalysis, ChatDotRound } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()

const visitedRoutes = ref<Array<{ path: string; title: string }>>([])
const activeTab = ref(route.path)

// 路径 → 组件名映射（必须与各组件声明的 name 完全一致）
const pathToComponentName: Record<string, string> = {
  '/dashboard': 'Dashboard',
  '/data-collector': 'DataSources',
  '/strategy': 'Strategy',
  '/experiments': 'Experiments',
  '/gold-dashboard': 'GoldDashboard',
  '/backtest-analysis': 'BacktestAnalysis',
  '/realtime-analysis': 'RealtimeAnalysis',
  '/chat': 'Chat',
}

// 始终缓存仪表盘，其他页面按需加入
const cachedComponents = ref(['Dashboard'])

function addTab(path: string, title: string) {
  if (!visitedRoutes.value.find(tab => tab.path === path)) {
    visitedRoutes.value.push({ path, title })
  }
}

// 初始化默认标签
addTab('/dashboard', '仪表盘')

// 监听路由变化：添加标签，并把当前路由对应的组件加入缓存列表
watch(() => route.path, (newPath) => {
  activeTab.value = newPath
  const metaTitle = route.meta?.title as string | undefined
  const title = metaTitle || (typeof route.name === 'string' ? route.name : newPath)
  addTab(newPath, title)

  // 加入缓存
  const compName = pathToComponentName[newPath]
  if (compName && !cachedComponents.value.includes(compName)) {
    cachedComponents.value.push(compName)
  }
}, { immediate: true })

function handleTabClick(pane: any) {
  if (pane.paneName && pane.paneName !== route.path) {
    router.push(pane.paneName)
  }
}

function removeTab(targetPath: string) {
  if (targetPath === '/dashboard') return

  const index = visitedRoutes.value.findIndex(tab => tab.path === targetPath)
  if (index === -1) return

  // 如果关闭的是当前活动标签，跳转到前一个标签（或仪表盘）
  if (targetPath === activeTab.value) {
    let nextTab = visitedRoutes.value[index - 1]
    if (!nextTab) {
      nextTab = visitedRoutes.value[index + 1] || visitedRoutes.value[0]
    }
    if (nextTab) {
      router.push(nextTab.path)
    }
  }

  // 从缓存列表中移除该组件（关键：关闭标签即销毁缓存）
  const compName = pathToComponentName[targetPath]
  if (compName) {
    const cacheIdx = cachedComponents.value.indexOf(compName)
    if (cacheIdx > -1) cachedComponents.value.splice(cacheIdx, 1)
  }

  // 移除标签
  visitedRoutes.value.splice(index, 1)
}
</script>

<style scoped>
.header-tabs {
  width: 100%;
}
.header-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
  border-bottom: none;
}
.header-tabs :deep(.el-tabs__nav) {
  border: none;
}
</style>