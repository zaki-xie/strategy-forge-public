<template>
  <div style="padding: 20px;">
    <h2>黄金价格走势</h2>
    <p style="color: #909399; font-size: 14px; margin-bottom: 16px;">
      数据来源：AU9999 收盘价、华安黄金ETF联接C、ETF518880（净值×100）、上海金交所、国际金价(GoldAPI，已按美元/盎司 × 7.15 / 31.1035 换算为人民币/克)
    </p>

    <div style="margin-bottom: 12px; display: flex; align-items: center; gap: 12px;">
      <el-radio-group v-model="freq" @change="fetchData" size="small">
        <el-radio-button label="D">日线</el-radio-button>
        <el-radio-button label="W">周线</el-radio-button>
        <el-radio-button label="M">月线</el-radio-button>
      </el-radio-group>
      <el-button @click="fetchData" :loading="loading" size="small">刷新</el-button>
    </div>

    <el-card shadow="never">
      <div ref="chartRef" style="width: 100%; height: 500px;" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'GoldDashboard' })
import { ref, onMounted, onBeforeUnmount, watch, nextTick, onActivated } from 'vue'
import * as echarts from 'echarts'
import { getGoldPrices } from '@/api/dataView'
import { ElMessage } from 'element-plus'

const chartRef = ref<HTMLElement>()
let chartInstance: echarts.ECharts | null = null
const loading = ref(false)
const freq = ref('D')

const colorPalette = [
  '#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de'
]

function initChart() {
  if (!chartRef.value) return
  chartInstance = echarts.init(chartRef.value)
}

async function fetchData() {
  loading.value = true
  try {
    const res = await getGoldPrices(freq.value)
    if (res.code === 0 && res.data) {
      renderChart(res.data)
    } else {
      ElMessage.error(res.message || '获取数据失败')
    }
  } catch (err) {
    console.error(err)
    ElMessage.error('网络请求失败')
  } finally {
    loading.value = false
  }
}

function renderChart(data: { dates: string[]; series: Record<string, (number | null)[]> }) {
  if (!chartInstance) initChart()
  if (!chartInstance) return

  const names = Object.keys(data.series)
  const option: echarts.EChartsOption = {
    animation: false,  // 关闭切换动画，防止数据频率切换过大导致的动画bug 
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' }
    },
    legend: {
      data: names,
      bottom: 0
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '18%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: data.dates,
      boundaryGap: false
    },
    yAxis: {
      type: 'value',
      name: '价格（元）',
      scale: true
    },
    dataZoom: [
      { type: 'inside', start: 0, end: 100 },
      { type: 'slider', bottom: 30 }
    ],
    series: names.map((name, idx) => ({
      name,
      type: 'line',
      data: data.series[name],
      connectNulls: true,
      showSymbol: false,
      lineStyle: { width: 2 },
      itemStyle: { color: colorPalette[idx % colorPalette.length] }
    }))
  }
  chartInstance.setOption(option, true)
}

// 窗口自适应
const resizeHandler = () => chartInstance?.resize()
onMounted(() => {
  initChart()
  fetchData()
  window.addEventListener('resize', resizeHandler)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeHandler)
  chartInstance?.dispose()
})

onActivated(() => {
  resizeHandler()
})

watch(freq, () => {
  nextTick(() => fetchData())
})
</script>