import { createRouter, createWebHistory } from 'vue-router'
import MainLayout from '@/layouts/MainLayout.vue'
import Dashboard from '@/views/Dashboard.vue'
import DataSources from '@/views/DataSources.vue'
import Strategy from '@/views/Strategy.vue'

const routes = [
  {
    path: '/',
    component: MainLayout,
    redirect: '/dashboard',
    children: [
      {
        path: '/dashboard',
        name: 'Dashboard',
        component: Dashboard,
        meta: { title: '仪表盘' }
      },
      {
        path: '/data-collector',
        name: 'DataSources',
        component: DataSources,
        meta: { title: '数据采集' }
      },
      {
        path: '/strategy',
        name: 'Strategy',
        component: Strategy,
        meta: { title: '策略中心' }
      },
      {
        path: '/experiments',
        name: 'Experiments',
        component: () => import('@/views/Experiments.vue'),
        meta: { title: '实验总览' }
      },
      {
        path: '/gold-dashboard',
        name: 'GoldDashboard',
        component: () => import('@/views/GoldDashboard.vue'),
        meta: { title: '黄金价格' }
      },
      {
        path: '/backtest-analysis',
        name: 'BacktestAnalysis',
        component: () => import('@/views/BacktestAnalysis.vue'),
        meta: { title: '回测分析' }
      },
      {
        path: '/realtime-analysis',
        name: 'RealtimeAnalysis',
        component: () => import('@/views/RealtimeAnalysis.vue'),
        meta: { title: '实盘分析' }
      },
      {
        path: '/chat',
        name: 'Chat',
        component: () => import('@/views/Chat.vue'),
        meta: { title: '量化助手' }
      }
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router