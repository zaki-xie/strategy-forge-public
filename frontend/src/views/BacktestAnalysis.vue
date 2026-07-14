<template>
  <div style="height: 100%; display: flex; flex-direction: column; padding: 5px; box-sizing: border-box;">
    <h2 style="margin: 0 0 5px 0; flex-shrink: 0;">回测分析</h2>

    <!-- 选择器行 -->
    <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 16px; flex-shrink: 0;">
      <span style="white-space: nowrap;">选择实验：</span>
      <el-select
        v-model="selectedExpId"
        @change="loadBacktestData"
        placeholder="请选择实验"
        :loading="loadingExpList"
        filterable
      >
        <el-option
          v-for="exp in experiments"
          :key="exp.id"
          :label="`#${exp.id} - ${exp.experiment_name}`"
          :value="exp.id"
        />
      </el-select>
      <el-button @click="loadBacktestData" :loading="loading">加载数据</el-button>
      <!-- <el-button @click="fetchExperiments" :loading="loadingExpList">加载实验列表</el-button> -->
    </div>

    <!-- 绩效 & 交易统计 & 仓位快照 - 统一左对齐 flex 布局 -->
    <div
      v-if="backtestData"
      style="display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 16px; flex-shrink: 0;"
    >
      <!-- 年化收益 -->
      <el-card shadow="never" style="max-width: 380px; flex: 0 0 auto; min-width: 240px;">
        <template #header>
          <span style="font-weight: 600;">年化收益</span>
        </template>
        <div style="display: flex; justify-content: space-between; padding: 4px 0;">
          <span>策略</span>
          <span style="font-weight: bold; color: #409EFF;">
            {{ backtestData.performance.strategy_total_return }}
          </span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 4px 0; border-top: 1px solid #ebeef5;">
          <span>基准</span>
          <span style="font-weight: bold; color: #909399;">
            {{ backtestData.performance.benchmark_total_return }}
          </span>
        </div>
      </el-card>

      <!-- 夏普比率 -->
      <el-card shadow="never" style="max-width: 380px; flex: 0 0 auto; min-width: 240px;">
        <template #header>
          <span style="font-weight: 600;">夏普比率</span>
        </template>
        <div style="display: flex; justify-content: space-between; padding: 4px 0;">
          <span>策略</span>
          <span style="font-weight: bold; color: #409EFF;">
            {{ backtestData.performance.strategy_sharpe?.toFixed(2) ?? '-' }}
          </span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 4px 0; border-top: 1px solid #ebeef5;">
          <span>基准</span>
          <span style="font-weight: bold; color: #909399;">
            {{ backtestData.performance.benchmark_sharpe?.toFixed(2) ?? '-' }}
          </span>
        </div>
      </el-card>

      <!-- 最大回撤 -->
      <el-card shadow="never" style="max-width: 380px; flex: 0 0 auto; min-width: 240px;">
        <template #header>
          <span style="font-weight: 600;">最大回撤</span>
        </template>
        <div style="display: flex; justify-content: space-between; padding: 4px 0;">
          <span>策略</span>
          <span style="font-weight: bold; color: #409EFF;">
            {{ backtestData.performance.strategy_max_dd }}
          </span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 4px 0; border-top: 1px solid #ebeef5;">
          <span>基准</span>
          <span style="font-weight: bold; color: #909399;">
            {{ backtestData.performance.benchmark_max_dd }}
          </span>
        </div>
      </el-card>

      <!-- 交易统计 -->
      <el-card shadow="never" style="max-width: 380px; flex: 0 0 auto; min-width: 240px;">
        <template #header>
          <span style="font-weight: 600;">交易统计</span>
        </template>
        <div style="display: flex; justify-content: space-between; padding: 4px 0;">
          <span>买入次数</span>
          <span style="font-weight: bold; color: #409EFF;">{{ backtestData.buy_count }}</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 4px 0; border-top: 1px solid #ebeef5;">
          <span>卖出次数</span>
          <span style="font-weight: bold; color: #409EFF;">{{ backtestData.sell_count }}</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 4px 0; border-top: 1px solid #ebeef5;">
          <span>平均持仓天数</span>
          <span style="font-weight: bold; color: #409EFF;">{{ backtestData.avg_hold_days?.toFixed(1) ?? '-' }}</span>
        </div>
      </el-card>

      <!-- 最新仓位快照 -->
      <el-card
        shadow="never"
        style="max-width: 380px; flex: 0 0 auto; min-width: 240px;"
        :body-style="{ padding: '6px 16px' }"
      >
        <template #header>
            <span style="font-weight: 600;">最新仓位快照</span>
        </template>
        <div style="display: flex; justify-content: space-between; padding: 2px 0;">
          <span>日期</span>
          <span style="font-weight: bold; color: #409EFF;">{{ backtestData.latest_snapshot.date }}</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #ebeef5;">
          <span>信号</span>
          <span style="font-weight: bold; color: #409EFF;">{{ backtestData.latest_snapshot.signal }}</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #ebeef5;">
          <span>当前仓位</span>
          <span style="font-weight: bold; color: #409EFF;">{{ backtestData.latest_snapshot.current_position }}</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #ebeef5;">
          <span>策略净值</span>
          <span style="font-weight: bold; color: #409EFF;">{{ backtestData.latest_snapshot.strategy_nav }}</span>
        </div>
      </el-card>

      <!-- 策略参数 -->
      <el-card shadow="never" style="max-width: 380px; flex: 0 0 auto; min-width: 240px;"  :body-style="{ padding: '6px 16px' }">
        <template #header>
          <span style="font-weight: 600;">策略参数</span>
        </template>
        <div style="display: flex; justify-content: space-between; padding: 2px 0;">
          <span>分割比例</span>
          <span style="font-weight: bold; color: #409EFF;">
            {{ backtestData.spilt_train_params.split_ratio }}
          </span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #ebeef5;">
          <span>OLS 窗口</span>
          <span style="font-weight: bold; color: #409EFF;">
            {{ backtestData.spilt_train_params.ols_window }} 周
          </span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #ebeef5;">
          <span>Z-Score 窗口</span>
          <span style="font-weight: bold; color: #409EFF;">
            {{ backtestData.spilt_train_params.zscore_window }} 周
          </span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #ebeef5;">
          <span>买入阈值</span>
          <span style="font-weight: bold; color: #409EFF;">
            {{ backtestData.spilt_train_params.buy_threshold }}
          </span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #ebeef5;">
          <span>卖出阈值</span>
          <span style="font-weight: bold; color: #409EFF;">
            {{ backtestData.spilt_train_params.sell_threshold }}
          </span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 2px 0; border-top: 1px solid #ebeef5;">
          <span>锁定分割日</span>
          <span style="font-weight: bold; color: #409EFF;">{{ backtestData.spilt_train_params.split_cutoff_date || '无' }}</span>
        </div>
      </el-card>

    </div>

    <el-collapse style="margin-top: 5px;">
      <el-collapse-item title="交易明细 (点击展开)">
        <el-table :data="tradeDetails" border stripe size="small" max-height="300">
          <el-table-column prop="buyDate" label="买入日期" width="120" />
          <el-table-column prop="buyPrice" label="买入价" width="100" />
          <el-table-column prop="sellDate" label="卖出日期" width="120" />
          <el-table-column prop="sellPrice" label="卖出价" width="100" />
          <el-table-column prop="holdDays" label="持有天数" width="100" />
          <el-table-column prop="returnRate" label="收益率" width="100">
            <template #default="{ row }">
              <span :style="{ color: row.returnRate > 0 ? '#67C23A' : '#F56C6C' }">
                {{ (row.returnRate * 100).toFixed(2) }}%
              </span>
            </template>
          </el-table-column>
        </el-table>
      </el-collapse-item>
    </el-collapse>

    <!-- 净值曲线 -->
    <el-card shadow="never" style="margin-bottom: 16px; flex-shrink: 0;">
      <h4 style="margin: 0 0 8px 0;">净值曲线</h4>
      <div ref="navChartRef" style="width: 100%; height: 25vh; min-height: 25vh;" />
    </el-card>

    <!-- 回撤曲线 -->
    <el-card shadow="never" style="flex-shrink: 0;">
      <h4 style="margin: 0 0 8px 0;">回撤曲线</h4>
      <div ref="ddChartRef" style="width: 100%; height: 25vh; min-height: 25vh;" />
    </el-card>


  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'BacktestAnalysis' })
import { ref, onMounted, nextTick, computed, onActivated, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'
import { getExperiments } from '@/api/experiment'
import { getBacktestData, type BacktestEquityData } from '@/api/dataView'
import { ElMessage } from 'element-plus'

interface ExperimentOption {
  id: number
  experiment_name: string
  status: string
}

const experiments = ref<ExperimentOption[]>([])
const loadingExpList = ref(false)
const selectedExpId = ref<number | null>(null)
const backtestData = ref<BacktestEquityData | null>(null)
const loading = ref(false)

const navChartRef = ref<HTMLElement>()
const ddChartRef = ref<HTMLElement>()
let navChart: echarts.ECharts | null = null
let ddChart: echarts.ECharts | null = null

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

async function loadBacktestData() {
  if (!selectedExpId.value) return
  loading.value = true
  try {
    const res = await getBacktestData(selectedExpId.value)
    backtestData.value = res.data
    await nextTick()
    renderCharts()
  } catch (err: any) {
    ElMessage.error(err.response?.data?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function renderCharts() {
  if (!backtestData.value) return
  renderNavChart()
  renderDDChart()
}

function renderNavChart() {
  if (!navChartRef.value) return
  if (!navChart) navChart = echarts.init(navChartRef.value)
  const data = backtestData.value!

  // 1. 构建买入、卖出日期的直接价格映射
  const buyMap: Record<string, number> = {}
  data.trade_signals.buy.forEach(item => { buyMap[item.date] = item.price })
  const sellMap: Record<string, number> = {}
  data.trade_signals.sell.forEach(item => { sellMap[item.date] = item.price })

  // 2. 按顺序配对买卖点，构建卖出 → 上一买入的映射
  const sellToBuyMap: Record<string, { buyDate: string; buyPrice: number }> = {}
  const buys = data.trade_signals.buy
  const sells = data.trade_signals.sell
  const pairCount = Math.min(buys.length, sells.length)
  for (let i = 0; i < pairCount; i++) {
    sellToBuyMap[sells[i].date] = {
      buyDate: buys[i].date,
      buyPrice: buys[i].price
    }
  }

  // 3. 构建图表标记数据（保持不变）
  const buyMarkers = data.trade_signals.buy.map(item => ({
    name: '买入',
    coord: [item.date, item.price] as [string, number],
    value: '买入',
    itemStyle: { color: '#67C23A' },
    symbol: 'triangle',
    symbolSize: 12,
    label: {
      show: true,
      position: 'top',
      formatter: `B\n${item.price.toFixed(4)}`,
      fontSize: 10,
      color: '#fff'
    }
  }))
  const sellMarkers = data.trade_signals.sell.map(item => ({
    name: '卖出',
    coord: [item.date, item.price] as [string, number],
    value: '卖出',
    itemStyle: { color: '#F56C6C' },
    symbol: 'triangle',
    symbolRotate: 180,
    symbolSize: 12,
    label: {
      show: true,
      position: 'bottom',
      formatter: `S\n${item.price.toFixed(4)}`,
      fontSize: 10,
      color: '#fff'
    }
  }))

  const option: echarts.EChartsOption = {
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        if (!params || params.length === 0) return ''
        const date = params[0].axisValue
        let result = `<div style="font-weight:600;">${date}</div>`

        // 曲线数值
        params.forEach((p: any) => {
          result += `<div>${p.marker} ${p.seriesName}: ${Number(p.value).toFixed(4)}</div>`
        })

        // 买入点信息
        if (buyMap[date] !== undefined) {
          result += `<div style="color:#67C23A; font-weight:bold; margin-top:4px;">买入: ${buyMap[date].toFixed(4)}</div>`
        }

        // 卖出点信息 + 配对买入信息
        if (sellMap[date] !== undefined) {
          result += `<div style="color:#F56C6C; font-weight:bold; margin-top:4px;">卖出: ${sellMap[date].toFixed(4)}</div>`
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
    yAxis: {
      type: 'value',
      name: '净值',
      scale: true,
      axisLabel: { formatter: (val: number) => val.toFixed(4) }
    },
    dataZoom: [
      { type: 'inside', start: 0, end: 100 },
      { type: 'slider', bottom: 25 }
    ],
    series: [
      {
        name: '策略净值',
        type: 'line',
        data: data.strategy_nav,
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
        data: data.benchmark_nav,
        connectNulls: true,
        showSymbol: false,
        lineStyle: { width: 1.5, type: 'dashed' }
      }
    ] as any[]
  }
  navChart.setOption(option)
}

function renderDDChart() {
  if (!ddChartRef.value) return
  if (!ddChart) ddChart = echarts.init(ddChartRef.value)
  const data = backtestData.value!
  const option: echarts.EChartsOption = {
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        let result = params[0]?.axisValue + '<br/>'
        params.forEach((p: any) => {
          result += `${p.marker} ${p.seriesName}: ${Number(p.value).toFixed(2)}%<br/>`
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
      axisLabel: {
        formatter: (val: number) => val.toFixed(2) + '%'   // 数据已是百分数，直接加 %
      }
    },
    dataZoom: [
      { type: 'inside', start: 0, end: 100 },
      { type: 'slider', bottom: 25 }
    ],
    series: [
      {
        name: '策略回撤',
        type: 'line',
        areaStyle: { color: 'rgba(238, 102, 102, 0.2)' },
        data: data.strategy_dd.map((v) => v * 100),   // 注意：传入的是百分数，如 3.62
        connectNulls: true,
        showSymbol: false
      },
      {
        name: '基准回撤',
        type: 'line',
        areaStyle: { color: 'rgba(102, 102, 238, 0.1)' },
        data: data.benchmark_dd.map((v) => v * 100),
        connectNulls: true,
        showSymbol: false,
        lineStyle: { type: 'dashed' }
      }
    ]
  }
  ddChart.setOption(option)
}

const tradeDetails = computed(() => {
  const buys = backtestData.value?.trade_signals.buy || []
  const sells = backtestData.value?.trade_signals.sell || []
  const pairs = []
  const count = Math.min(buys.length, sells.length)
  for (let i = 0; i < count; i++) {
    const buy = buys[i]
    const sell = sells[i]
    pairs.push({
      buyDate: buy.date,
      buyPrice: buy.price,
      sellDate: sell.date,
      sellPrice: sell.price,
      holdDays: (new Date(sell.date).getTime() - new Date(buy.date).getTime()) / (1000 * 3600 * 24),
      returnRate: (sell.price - buy.price) / buy.price
    })
  }
  return pairs
})

const resizeHandler = () => {
  navChart?.resize()
  ddChart?.resize()
}

onMounted(() => {
  window.addEventListener('resize', resizeHandler)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeHandler)
  navChart?.dispose()
  ddChart?.dispose()
})
// 组件被缓存在 keep-alive 中，每次切回时重新加载数据
onActivated(() => {
  fetchExperiments()
  resizeHandler()
})
</script>