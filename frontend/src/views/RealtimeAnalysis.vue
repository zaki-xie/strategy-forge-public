<template>
  <div style="height: 100%; display: flex; flex-direction: column; padding: 20px; box-sizing: border-box; overflow-y: auto;">
    <h2 style="margin: 0 0 8px 0;">实盘分析</h2>

    <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 16px;">
      <span style="white-space: nowrap;">选择实验：</span>
      <el-select v-model="selectedExpId" @change="loadRealtimeData" placeholder="请选择实验" :loading="loadingExpList" filterable>
        <el-option v-for="exp in experiments" :key="exp.id" :label="`#${exp.id} - ${exp.experiment_name}`" :value="exp.id" />
      </el-select>
      <el-button @click="loadRealtimeData" :loading="loading">加载数据</el-button>
    </div>

    <!-- 绩效卡片 -->
    <div v-if="realtimeData" style="display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 16px;">
      <!-- 实盘绩效（6项） -->
      <el-card shadow="never" style="max-width: 380px; flex: 0 0 auto; min-width: 240px;">
        <template #header><span style="font-weight: 600;">实盘绩效</span></template>
        <div style="display: flex; justify-content: space-between; padding: 2px 0;">
          <span>最终总资产</span>
          <span style="font-weight: bold; color: #409EFF;">{{ realtimeData.performance.final_total }} 元</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #ebeef5;">
          <span>最终净值</span>
          <span style="font-weight: bold; color: #409EFF;">{{ realtimeData.performance.final_nav }}</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #ebeef5;">
          <span>年化收益率</span>
          <span style="font-weight: bold; color: #409EFF;">{{ realtimeData.performance.annual_return }}</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #ebeef5;">
          <span>夏普比率</span>
          <span style="font-weight: bold; color: #409EFF;">{{ realtimeData.performance.sharpe?.toFixed(2) ?? '-' }}</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #ebeef5;">
          <span>最大回撤</span>
          <span style="font-weight: bold; color: #409EFF;">{{ realtimeData.performance.max_drawdown }}</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #ebeef5;">
          <span>总手续费</span>
          <span style="font-weight: bold; color: #409EFF;">{{ realtimeData.performance.fee_total }} 元</span>
        </div>
      </el-card>

      <!-- 基准绩效（买入后一直持有） -->
      <el-card shadow="never" style="max-width: 380px; flex: 0 0 auto; min-width: 240px;">
        <template #header><span style="font-weight: 600;">基准绩效（买入持有）</span></template>
        <div style="display: flex; justify-content: space-between; padding: 2px 0;">
          <span>最终总资产</span>
          <span style="font-weight: bold; color: #409EFF;">{{ realtimeData.performance.benchmark_final_total ?? '-' }} 元</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #ebeef5;">
          <span>年化收益率</span>
          <span style="font-weight: bold; color: #409EFF;">{{ realtimeData.performance.benchmark_annual_return ?? '-' }}</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #ebeef5;">
          <span>夏普比率</span>
          <span style="font-weight: bold; color: #409EFF;">{{ realtimeData.performance.benchmark_sharpe?.toFixed(2) ?? '-' }}</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #ebeef5;">
          <span>最大回撤</span>
          <span style="font-weight: bold; color: #409EFF;">{{ realtimeData.performance.benchmark_max_drawdown ?? '-' }}</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #ebeef5;">
          <span>最终净值</span>
          <span style="font-weight: bold; color: #409EFF;">{{ realtimeData.performance.benchmark_nav_end ?? '-' }}</span>
        </div>
      </el-card>

      <!-- 交易统计（5项） -->
      <el-card shadow="never" style="max-width: 380px; flex: 0 0 auto; min-width: 240px;">
        <template #header><span style="font-weight: 600;">交易统计</span></template>
        <div style="display: flex; justify-content: space-between; padding: 2px 0;">
          <span>买入次数</span>
          <span style="font-weight: bold; color: #409EFF;">{{ realtimeData.trade_stats.buy_count }}</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #ebeef5;">
          <span>卖出次数</span>
          <span style="font-weight: bold; color: #409EFF;">{{ realtimeData.trade_stats.sell_count }}</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #ebeef5;">
          <span>总交易次数</span>
          <span style="font-weight: bold; color: #409EFF;">{{ realtimeData.trade_stats.total_trades }}</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #ebeef5;">
          <span>平均持仓天数</span>
          <span style="font-weight: bold; color: #409EFF;">{{ realtimeData.trade_stats.avg_hold_days?.toFixed(1) ?? '-' }}</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #ebeef5;">
          <span>总手续费</span>
          <span style="font-weight: bold; color: #409EFF;">{{ realtimeData.trade_stats.total_fee }} 元</span>
        </div>
      </el-card>

      <!-- 当前仓位（补全 total_asset 和 nav_real） -->
      <el-card shadow="never" style="max-width: 380px; flex: 0 0 auto; min-width: 240px;">
        <template #header><span style="font-weight: 600;">当前仓位</span></template>
        <div style="display: flex; justify-content: space-between; padding: 2px 0;">
          <span>日期</span>
          <span style="font-weight: bold; color: #409EFF;">{{ realtimeData.current_account.date }}</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #ebeef5;">
          <span>现金</span>
          <span style="font-weight: bold; color: #409EFF;">{{ realtimeData.current_account.cash }} 元</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #ebeef5;">
          <span>份额</span>
          <span style="font-weight: bold; color: #409EFF;">{{ realtimeData.current_account.shares }}</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #ebeef5;">
          <span>总资产</span>
          <span style="font-weight: bold; color: #409EFF;">{{ realtimeData.current_account.total_asset }} 元</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #ebeef5;">
          <span>实盘净值</span>
          <span style="font-weight: bold; color: #409EFF;">{{ realtimeData.current_account.nav_real }}</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #ebeef5;">
          <span>仓位状态</span>
          <span style="font-weight: bold; color: #409EFF;">{{ realtimeData.current_account.position }}</span>
        </div>
      </el-card>

      <!-- 回测对比 -->
      <el-card shadow="never" style="max-width: 380px; flex: 0 0 auto; min-width: 240px;">
        <template #header><span style="font-weight: 600;">回测对比</span></template>
        <div style="display: flex; justify-content: space-between; padding: 2px 0;">
          <span>回测策略净值(终)</span>
          <span style="font-weight: bold; color: #409EFF;">{{ realtimeData.performance.backtest_strategy_nav_end ?? '无' }}</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #ebeef5;">
          <span>回测基准净值(终)</span>
          <span style="font-weight: bold; color: #409EFF;">{{ realtimeData.performance.backtest_benchmark_nav_end ?? '无' }}</span>
        </div>
      </el-card>

      <!-- 信号分布 -->
      <el-card shadow="never" style="max-width: 380px; flex: 0 0 auto; min-width: 240px;">
        <template #header><span style="font-weight: 600;">信号分布</span></template>
        <div
          v-for="(count, signal) in realtimeData.trade_stats.signal_distribution"
          :key="signal"
          style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #ebeef5;"
        >
          <span>{{ signalMap[signal] ?? signal }}</span>
          <span style="font-weight: bold; color: #409EFF;">{{ count }}</span>
        </div>
        <div v-if="!realtimeData.trade_stats.signal_distribution || Object.keys(realtimeData.trade_stats.signal_distribution).length === 0" style="text-align: center; color: #909399;">
          暂无信号数据
        </div>
      </el-card>

      <!-- 最大回撤区间 -->
      <el-card shadow="never" style="max-width: 380px; flex: 0 0 auto; min-width: 240px;">
        <template #header><span style="font-weight: 600;">最大回撤区间</span></template>
        <div style="display: flex; justify-content: space-between; padding: 2px 0;">
          <span>起始日期</span>
          <span style="font-weight: bold; color: #409EFF;">{{ realtimeData.max_drawdown_info.start_date }}</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #ebeef5;">
          <span>结束日期</span>
          <span style="font-weight: bold; color: #409EFF;">{{ realtimeData.max_drawdown_info.end_date }}</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #ebeef5;">
          <span>回撤幅度</span>
          <span style="font-weight: bold; color: #409EFF;">{{ realtimeData.max_drawdown_info.drawdown }}</span>
        </div>
      </el-card>
    </div>

    <!-- 最近交易明细（可折叠） -->
    <el-collapse v-if="realtimeData && realtimeData.recent_trades.length > 0" style="margin-bottom: 16px;">
      <el-collapse-item title="最近交易明细（5笔）">
        <el-table :data="realtimeData.recent_trades" border stripe size="small" max-height="250">
          <el-table-column prop="buy_date" label="买入日期" width="120" />
          <el-table-column prop="buy_price" label="买入价格" width="120">
            <template #default="{ row }">{{ row.buy_price?.toFixed(4) }}</template>
          </el-table-column>
          <el-table-column prop="sell_date" label="卖出日期" width="120">
            <template #default="{ row }">{{ row.sell_date || '持仓中' }}</template>
          </el-table-column>
          <el-table-column prop="sell_price" label="卖出价格" width="120">
            <template #default="{ row }">{{ row.sell_price != null ? row.sell_price.toFixed(4) : '-' }}</template>
          </el-table-column>
          <el-table-column prop="hold_days" label="持有天数" width="100">
            <template #default="{ row }">{{ row.hold_days ?? '-' }}</template>
          </el-table-column>
        </el-table>
      </el-collapse-item>
    </el-collapse>

    <!-- 曲线图（Tab切换） -->
    <el-card shadow="never" style="flex: 1; display: flex; flex-direction: column; min-height: 350px; margin-bottom: 0;">
      <el-tabs v-model="activeChartTab" @tab-change="handleTabChange" class="chart-tabs">
        <el-tab-pane label="净值曲线" name="nav">
          <div ref="navChartRef" style="width: 100%; height: 100%; min-height: 0;" />
        </el-tab-pane>
        <el-tab-pane label="回撤曲线" name="dd">
          <div ref="ddChartRef" style="width: 100%; height: 100%; min-height: 0;" />
        </el-tab-pane>
        <el-tab-pane label="账户资产曲线" name="cf">
          <div ref="cfChartRef" style="width: 100%; height: 100%; min-height: 0;" />
        </el-tab-pane>
        <el-tab-pane label="基金净值变化曲线" name="fund">
          <div ref="fundChartRef" style="width: 100%; height: 100%; min-height: 0;" />
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick, onActivated, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'
import { getExperiments } from '@/api/experiment'
import { getRealtimeData, type RealtimeEquityData } from '@/api/dataView'
import { ElMessage } from 'element-plus'

defineOptions({ name: 'RealtimeAnalysis' })

interface ExperimentOption { id: number; experiment_name: string; status: string }

const experiments = ref<ExperimentOption[]>([])
const loadingExpList = ref(false)
const selectedExpId = ref<number | null>(null)
const realtimeData = ref<RealtimeEquityData | null>(null)
const loading = ref(false)

const navChartRef = ref<HTMLElement>()
const ddChartRef = ref<HTMLElement>()
const cfChartRef = ref<HTMLElement>()
const fundChartRef = ref<HTMLElement>()

let navChart: echarts.ECharts | null = null
let ddChart: echarts.ECharts | null = null
let cfChart: echarts.ECharts | null = null
let fundChart: echarts.ECharts | null = null

const signalMap: Record<string, string> = {
  '1': '买入',
  '-1': '卖出',
  '0': '持有'
}

const activeChartTab = ref('nav')

async function fetchExperiments() {
  loadingExpList.value = true
  try {
    const res = await getExperiments()
    experiments.value = (res.data.experiments || []).filter((e: any) =>
      ['backtested', 'realtimed'].includes(e.status)
    )
  } catch (e) {
    console.error(e)
  } finally {
    loadingExpList.value = false
  }
}

async function loadRealtimeData() {
  if (!selectedExpId.value) return
  loading.value = true
  try {
    const res = await getRealtimeData(selectedExpId.value)
    realtimeData.value = res.data
    await nextTick()
    renderCharts()
  } catch (err: any) {
    ElMessage.error(err.response?.data?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function renderCharts() {
  if (!realtimeData.value) return
  // 只渲染当前激活的 tab 图表，避免未显示的容器初始化错误
  if (activeChartTab.value === 'nav') renderNavChart()
  else if (activeChartTab.value === 'dd') renderDDChart()
  else if (activeChartTab.value === 'cf') renderCFChart()
  else if (activeChartTab.value === 'fund') renderFundChart()   // 添加此行
}

function renderNavChart() {
  if (!navChartRef.value) return
  if (!navChart) navChart = echarts.init(navChartRef.value)
  const data = realtimeData.value!

  // 日期 → 净值映射
  const navMap = new Map<string, number>()
  data.dates.forEach((d, i) => navMap.set(d, data.nav_real[i]))

  // 日期 → 买入/卖出价格映射
  const buyMap = new Map<string, number>()
  const sellMap = new Map<string, number>()
  data.buy_signals?.forEach(item => buyMap.set(item.date, item.price))
  data.sell_signals?.forEach(item => sellMap.set(item.date, item.price))

  // 构建卖出 → 配对买入的映射（按顺序配对）
  const sellToBuyMap: Record<string, { buyDate: string; buyPrice: number }> = {}
  const buys = data.buy_signals || []
  const sells = data.sell_signals || []
  for (let i = 0; i < Math.min(buys.length, sells.length); i++) {
    sellToBuyMap[sells[i].date] = {
      buyDate: buys[i].date,
      buyPrice: buys[i].price
    }
  }

  // 构建买卖点标记
  const buyMarkers = buys.map(item => {
    const navVal = navMap.get(item.date) ?? 0
    return {
      name: '买入',
      coord: [item.date, navVal] as [string, number],
      value: `买入\n净值: ${navVal.toFixed(4)}\n份额价: ${item.price.toFixed(4)}`,
      itemStyle: { color: '#67C23A' },
      symbol: 'triangle',
      symbolSize: 12,
      label: {
        show: true,
        position: 'top',
        formatter: `B\n${item.price.toFixed(4)}`,
        fontSize: 10,
        color: '#67C23A'
      }
    }
  })
  const sellMarkers = sells.map(item => {
    const navVal = navMap.get(item.date) ?? 0
    return {
      name: '卖出',
      coord: [item.date, navVal] as [string, number],
      value: `卖出\n净值: ${navVal.toFixed(4)}\n份额价: ${item.price.toFixed(4)}`,
      itemStyle: { color: '#F56C6C' },
      symbol: 'triangle',
      symbolRotate: 180,
      symbolSize: 12,
      label: {
        show: true,
        position: 'bottom',
        formatter: `S\n${item.price.toFixed(4)}`,
        fontSize: 10,
        color: '#F56C6C'
      }
    }
  })

  const option: echarts.EChartsOption = {
     tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        const date = params[0].axisValue
        let result = `<div style="font-weight:600;">${date}</div>`
        params.forEach((p: any) => {
          result += `${p.marker} ${p.seriesName}: ${Number(p.value).toFixed(4)}<br/>`
        })
        // 附加买卖点信息
        const buyPrice = buyMap.get(date)
        if (buyPrice !== undefined) {
          result += `<div style="color:#67C23A; font-weight:bold; margin-top:4px;">买入基金净值: ${buyPrice.toFixed(4)}</div>`
        }
        const sellPrice = sellMap.get(date)
        if (sellPrice !== undefined) {
          result += `<div style="color:#F56C6C; font-weight:bold; margin-top:4px;">卖出基金净值: ${sellPrice.toFixed(4)}</div>`
          const pairedBuy = sellToBuyMap[date]
          if (pairedBuy) {
            result += `<div style="color:#E6A23C; font-size:12px; margin-top:2px;">↳ 买入 ${pairedBuy.buyDate} @ ${pairedBuy.buyPrice.toFixed(4)}</div>`
          }
        }
        return result
      }
    },
    legend: { top: 10, right: 10 },
    grid: { left: '3%', right: '4%', bottom: '18%', containLabel: true },
    xAxis: { type: 'category', data: data.dates, boundaryGap: false },
    yAxis: { type: 'value', name: '净值', scale: true },
    dataZoom: [
      { type: 'inside', start: 0, end: 100 },
      { type: 'slider', bottom: 10 }
    ],
    series: [
      {
        name: '实盘净值',
        type: 'line',
        data: data.nav_real,
        connectNulls: true,
        showSymbol: false,
        lineStyle: { width: 2 },
        markPoint: {
          symbol: 'pin',
          symbolSize: 30,
          data: [...buyMarkers, ...sellMarkers]
        }
      },
      {
        name: '基准净值',
        type: 'line',
        data: data.benchmark_nav,        // 新增
        connectNulls: true,
        showSymbol: false,
        lineStyle: { width: 2, type: 'dashed' }
      }
    ] as any[]
  }
  navChart.setOption(option)
  navChart.resize()
}

function renderDDChart() {
  if (!ddChartRef.value) return
  if (!ddChart) ddChart = echarts.init(ddChartRef.value)
  const data = realtimeData.value!
  const option: echarts.EChartsOption = {
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        let result = `${params[0].axisValue}<br/>`
        params.forEach((p: any) => {
          result += `${p.marker} ${p.seriesName}: ${(p.value * 100).toFixed(2)}%<br/>`
        })
        return result
      }
    },
    legend: { top: 10, right: 10 },
    grid: { left: '3%', right: '4%', bottom: '18%', containLabel: true },
    xAxis: { type: 'category', data: data.dates, boundaryGap: false },
    yAxis: {
      type: 'value',
      name: '回撤',
      axisLabel: { formatter: (val: number) => (val * 100).toFixed(2) + '%' }
    },
    dataZoom: [
      { type: 'inside', start: 0, end: 100 },
      { type: 'slider', bottom: 10 }
    ],
    series: [
      { 
        name: '实盘回撤', 
        type: 'line', 
        data: data.drawdown, 
        areaStyle: { color: 'rgba(238,102,102,0.2)' }, 
        connectNulls: true, 
        showSymbol: false 
      },
      {
        name: '基准回撤',
        type: 'line',
        data: data.benchmark_drawdown,        // 新增
        areaStyle: { color: 'rgba(102,102,238,0.15)' },
        connectNulls: true,
        showSymbol: false,
        lineStyle: { type: 'dashed' }
      }
    ]
  }
  ddChart.setOption(option)
  ddChart.resize()   // 新增
}

function renderCFChart() {
  if (!cfChartRef.value) return
  if (!cfChart) cfChart = echarts.init(cfChartRef.value)
  const data = realtimeData.value!
  const option: echarts.EChartsOption = {
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        let result = `${params[0].axisValue}<br/>`
        params.forEach((p: any) => {
          result += `${p.marker} ${p.seriesName}: ${Number(p.value).toFixed(4)}<br/>`
        })
        return result
      }
    },
    legend: { top: 10, right: 10 },
    grid: { left: '3%', right: '4%', bottom: '18%', containLabel: true },
    xAxis: { type: 'category', data: data.dates, boundaryGap: false },
    yAxis: { type: 'value', name: '金额/份额', scale: true },
    dataZoom: [
      { type: 'inside', start: 0, end: 100 },
      { type: 'slider', bottom: 10 }
    ],
    series: [
      { name: '现金', type: 'line', data: data.cash, connectNulls: true, showSymbol: false },
      { name: '份额', type: 'line', data: data.shares, connectNulls: true, showSymbol: false },
      { name: '总资产', type: 'line', data: data.total_asset, connectNulls: true, showSymbol: false, lineStyle: { width: 2 } },
      { name: '基准总资产', type: 'line', data: data.benchmark_total_asset, connectNulls: true, showSymbol: false, lineStyle: { type: 'dashed', width: 2 } }
    ]
  }
  cfChart.setOption(option)
  cfChart.resize()   // 新增
}

function renderFundChart() {
  if (!fundChartRef.value) return
  if (!fundChart) fundChart = echarts.init(fundChartRef.value)
  const data = realtimeData.value!
  const fund = data.fund_nav
  if (!fund || fund.dates.length === 0) return

  // 日期 → 基金净值映射（此处无需，因为 y 轴就是价格，但可用于其他计算）
  // 构建买卖日期映射
  const buyMap = new Map<string, number>()
  const sellMap = new Map<string, number>()
  data.buy_signals?.forEach(item => buyMap.set(item.date, item.price))
  data.sell_signals?.forEach(item => sellMap.set(item.date, item.price))

  // 构建卖出 → 买入配对映射
  const sellToBuyMap: Record<string, { buyDate: string; buyPrice: number }> = {}
  const buys = data.buy_signals || []
  const sells = data.sell_signals || []
  for (let i = 0; i < Math.min(buys.length, sells.length); i++) {
    sellToBuyMap[sells[i].date] = {
      buyDate: buys[i].date,
      buyPrice: buys[i].price
    }
  }

  // 构建买卖点标记（Y 轴直接使用交易价格）
  const buyMarkers = buys.map(item => ({
    name: '买入',
    coord: [item.date, item.price] as [string, number],
    value: `买入\n${item.price.toFixed(4)}`,
    itemStyle: { color: '#67C23A' },
    symbol: 'triangle',
    symbolSize: 12,
    label: {
      show: true,
      position: 'top',
      formatter: `B\n${item.price.toFixed(4)}`,
      fontSize: 10,
      color: '#67C23A'
    }
  }))
  const sellMarkers = sells.map(item => ({
    name: '卖出',
    coord: [item.date, item.price] as [string, number],
    value: `卖出\n${item.price.toFixed(4)}`,
    itemStyle: { color: '#F56C6C' },
    symbol: 'triangle',
    symbolRotate: 180,
    symbolSize: 12,
    label: {
      show: true,
      position: 'bottom',
      formatter: `S\n${item.price.toFixed(4)}`,
      fontSize: 10,
      color: '#F56C6C'
    }
  }))

  const option: echarts.EChartsOption = {
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        const p = params[0]
        const date = p.axisValue
        let result = `<div style="font-weight:600;">${date}</div>`
        result += `<div>基金净值: ${Number(p.value).toFixed(4)}</div>`

        const buyPrice = buyMap.get(date)
        if (buyPrice !== undefined) {
          result += `<div style="color:#67C23A; font-weight:bold; margin-top:4px;">买入: ${buyPrice.toFixed(4)}</div>`
        }

        const sellPrice = sellMap.get(date)
        if (sellPrice !== undefined) {
          result += `<div style="color:#F56C6C; font-weight:bold; margin-top:4px;">卖出: ${sellPrice.toFixed(4)}</div>`
          const pairedBuy = sellToBuyMap[date]
          if (pairedBuy) {
            result += `<div style="color:#E6A23C; font-size:12px; margin-top:2px;">↳ 买入 ${pairedBuy.buyDate} @ ${pairedBuy.buyPrice.toFixed(4)}</div>`
          }
        }

        return result
      }
    },
    legend: { top: 10, right: 10 },
    grid: { left: '3%', right: '4%', bottom: '18%', containLabel: true },
    xAxis: { type: 'category', data: fund.dates, boundaryGap: false },
    yAxis: { type: 'value', name: '净值', scale: true },
    dataZoom: [
      { type: 'inside', start: 0, end: 100 },
      { type: 'slider', bottom: 10 }
    ],
    series: [
      {
        name: '基金净值',
        type: 'line',
        data: fund.values,
        connectNulls: true,
        showSymbol: false,
        lineStyle: { width: 2 },
        markPoint: {
          symbol: 'pin',
          symbolSize: 30,
          data: [...buyMarkers, ...sellMarkers]
        }
      }
    ] as any[]
  }
  fundChart.setOption(option)
  fundChart.resize()
}

function handleTabChange(name: string) {
  nextTick(() => {
    if (name === 'nav') {
      if (!navChart) renderNavChart()
      else navChart.resize()
    } else if (name === 'dd') {
      if (!ddChart) renderDDChart()
      else ddChart.resize()
    } else if (name === 'cf') {
      if (!cfChart) renderCFChart()
      else cfChart.resize()
    } else if (name === 'fund') {
      if (!fundChart) renderFundChart()
      else fundChart.resize()
    }
  })
}



const resizeHandler = () => {
  navChart?.resize()
  ddChart?.resize()
  cfChart?.resize()
  fundChart?.resize()
}

onMounted(() => {
  
  window.addEventListener('resize', resizeHandler)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeHandler)
  navChart?.dispose()
  ddChart?.dispose()
  cfChart?.dispose()
  fundChart?.dispose()
})

// 组件被缓存在 keep-alive 中，每次切回时重新加载数据
onActivated(() => {
  fetchExperiments()
  resizeHandler()
})

</script>

<style scoped>
/* 让 el-tabs 完全填充父容器，内容区自动占满剩余空间 */
.chart-tabs {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.chart-tabs :deep(.el-tabs__content) {
  flex: 1;
  min-height: 0;
}
.chart-tabs :deep(.el-tab-pane) {
  height: 100%;
}
</style>