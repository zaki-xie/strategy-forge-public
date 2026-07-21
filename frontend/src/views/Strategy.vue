<template>
  <div style="padding: 20px;">
    <h2>策略中心</h2>

    <!-- 实验选择与操作按钮 -->
    <ExperimentSelector ref="expSelector" v-model="selectedExpId" style="margin-bottom: 20px;" />

    <!-- 最新信号卡片 -->
    <el-card v-if="latestSignal" shadow="hover" style="margin-bottom: 20px; max-width: 600px;">
      <template #header>
         <span style="font-weight: 600;">
            📡 最新交易信号 
            <span v-if="signalExperimentName" style="color: #409EFF;">
              ({{ signalExperimentName }})
            </span>
          </span>
      </template>
      <el-row :gutter="20">
        <el-col :span="12">
          <div style="margin-bottom: 8px;">
            <span style="color: #606266;">日期：</span>
            <span>{{ latestSignal.date }}</span>
          </div>
          <div style="margin-bottom: 8px;">
            <span style="color: #606266;">信号：</span>
            <el-tag :type="signalTagType(latestSignal.signal)" size="large">
              {{ signalText(latestSignal.signal) }}
            </el-tag>
          </div>
          <div style="margin-bottom: 8px;">
            <span style="color: #606266;">趋势：</span>
            <span>{{ latestSignal.trend === 1 ? '多头' : latestSignal.trend === 0 ? '空头' : '-' }}</span>
          </div>
        </el-col>
        <el-col :span="12">
          <div style="margin-bottom: 8px;">
            <span style="color: #606266;">预测收益率：</span>
            <span>{{ latestSignal.predicted_return?.toFixed(4) ?? '-' }}</span>
          </div>
          <div style="margin-bottom: 8px;">
            <span style="color: #606266;">Z-Score：</span>
            <span>{{ latestSignal.pred_zscore?.toFixed(2) ?? '-' }}</span>
          </div>
          <div style="margin-bottom: 8px;">
            <span style="color: #606266;">本周净值(NAV)：</span>
            <span>{{ latestSignal.nav?.toFixed(4) ?? '-' }}</span>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 操作按钮（根据实验状态启用/禁用） -->
    <el-button type="primary" @click="handlePreprocess" :loading="preprocessingLoading">
      运行数据预处理
    </el-button>
    <el-button type="primary" @click="handleWeeklyAggregateNew" :loading="weeklyAggregateNewLoading">
      运行周频聚合(新建实验)
    </el-button>
    <el-button type="primary" @click="handleWeeklyAggregate" :loading="weeklyAggregateLoading">
      运行周频聚合
    </el-button>

   <!-- 数据分割：有周频数据即可执行（状态 >= weekly_aggregator） -->
    <el-button
      type="primary"
      @click="handleSplitData"
      :loading="splitLoading"
      :disabled="!selectedExpId || !selectedExperiment?.weekly_dir"
      style="margin-left: 10px;"
    >
      执行数据分割
    </el-button>

    <!-- 滚动训练：有分割数据即可执行（状态 >= splitted） -->
    <el-button
      type="primary"
      @click="handleTrainOls"
      :loading="trainLoading"
      :disabled="!selectedExpId || !selectedExperiment?.split_dir"
      style="margin-left: 10px;"
    >
      执行滚动训练
    </el-button>

    <!-- 回测：有预测结果即可执行（状态 >= trained） -->
    <el-button
      type="primary"
      @click="handleBackTest"
      :loading="backtestLoading"
      :disabled="!selectedExpId || !selectedExperiment?.train_dir"
      style="margin-left: 10px;"
    >
      执行回测
    </el-button>

    <!-- 实盘模拟：有回测结果即可执行（状态 >= backtested） -->
    <el-button
      type="primary"
      @click="handleRealTime"
      :loading="realtimeLoading"
      :disabled="!selectedExpId || !selectedExperiment?.train_dir"
      style="margin-left: 10px;"
    >
      执行实盘模拟
    </el-button>

    <el-divider />

    <DataFileBrowser
      :allowedDirs="[DataDirTypeEnum.processed, DataDirTypeEnum.experiment]"
      :defaultDir="DataDirTypeEnum.processed"
    />
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'Strategy' })
import { ref, watch, computed } from 'vue'
import { runPreprocessing, runWeeklyAggregate, runSplitData, runTrainOLS, runBacktest, runRealtime } from '@/api/strategy'
import { ElMessage } from 'element-plus'
import { DataDirType, SortOrder } from '@/api/types'
import DataFileBrowser from '@/components/DataFileBrowser.vue'
import ExperimentSelector from '@/components/ExperimentSelector.vue'
import { latestMessage } from '@/composables/useGlobalWebSocket'
import { getFileData } from '@/api/dataView'          // 新增导入


const DataDirTypeEnum = DataDirType

// 选中的实验ID
const selectedExpId = ref<number | null>(null)
// 实验数据表
const expSelector = ref<InstanceType<typeof ExperimentSelector>>()

// 各操作加载状态
const preprocessingLoading = ref(false)
const weeklyAggregateNewLoading = ref(false)
const weeklyAggregateLoading = ref(false)
const splitLoading = ref(false)
const trainLoading = ref(false)
const backtestLoading = ref(false)
const realtimeLoading = ref(false)

// 选中实验名称（文件夹格式）
const signalExperimentName = ref<string>('')

async function handlePreprocess() {
  preprocessingLoading.value = true
  try {
    const res = await runPreprocessing()
    ElMessage({ message: res.message || '操作成功', type: 'success' })
  } catch (err: any) {
    ElMessage({ message: err.message || '操作失败', type: 'error' })
  } finally {
    preprocessingLoading.value = false
  }
}

async function handleWeeklyAggregateNew() {

  weeklyAggregateNewLoading.value = true
  try {
    // 如果已选中实验，则进行覆盖聚合，传入实验ID
    const res = await runWeeklyAggregate()
    ElMessage({ message: res.message || '周频聚合任务已启动', type: 'success' })
  } catch (err: any) {
    ElMessage({ message: err.message || '操作失败', type: 'error' })
  } finally {
    weeklyAggregateNewLoading.value = false
  }
}

// 周频聚合
async function handleWeeklyAggregate() {
  if (!selectedExpId.value) {
    ElMessage.warning('请先选择实验')
    return
  }
  weeklyAggregateLoading.value = true
  try {
    // 如果已选中实验，则进行覆盖聚合，传入实验ID
    const res = await runWeeklyAggregate(selectedExpId.value)
    ElMessage({ message: res.message || '周频聚合任务已启动', type: 'success' })
  } catch (err: any) {
    ElMessage({ message: err.message || '操作失败', type: 'error' })
  } finally {
    weeklyAggregateLoading.value = false
  }
}

// 数据分割
async function handleSplitData() {
  if (!selectedExpId.value) {
    ElMessage.warning('请先选择实验')
    return
  }
  splitLoading.value = true
  try {
    const res = await runSplitData(selectedExpId.value)
    ElMessage({ message: res.message || '数据分割已启动', type: 'success' })
  } catch (err: any) {
    ElMessage({ message: err.message || '操作失败', type: 'error' })
  } finally {
    splitLoading.value = false
  }
}

// 滚动训练
async function handleTrainOls() {
  if (!selectedExpId.value) {
    ElMessage.warning('请先选择实验')
    return
  }
  trainLoading.value = true
  try {
    const res = await runTrainOLS(selectedExpId.value)
    ElMessage({ message: res.message || '滚动训练已启动', type: 'success' })
  } catch (err: any) {
    ElMessage({ message: err.message || '操作失败', type: 'error' })
  } finally {
    trainLoading.value = false
  }
}

// 回测
async function handleBackTest() {
  if (!selectedExpId.value) {
    ElMessage.warning('请先选择实验')
    return
  }
  backtestLoading.value = true
  try {
    const res = await runBacktest(selectedExpId.value)
    ElMessage({ message: res.message || '回测已启动', type: 'success' })
  } catch (err: any) {
    ElMessage({ message: err.message || '操作失败', type: 'error' })
  } finally {
    backtestLoading.value = false
  }
}

// 实盘模拟
async function handleRealTime() {
  if (!selectedExpId.value) {
    ElMessage.warning('请先选择实验')
    return
  }
  backtestLoading.value = true
  try {
    const res = await runRealtime(selectedExpId.value)
    ElMessage({ message: res.message || '实盘模拟已启动', type: 'success' })
  } catch (err: any) {
    ElMessage({ message: err.message || '操作失败', type: 'error' })
  } finally {
    backtestLoading.value = false
  }
}



// WebSocket 监听任务完成事件
watch(latestMessage, async (msg) => {
  if (!msg) return
  const payload = msg.data || msg
  const task = payload.task
  console.log(msg._eventType)
  if(msg._eventType !== 'experiment_completed')
    return

  if (task === '数据周频聚合') {
    
  } else if (task === '训练/测试集划分') {

  } else if (task === '滚动OLS训练') {
    
  } else if (task === '回测模拟') {
    
  }

  await expSelector.value?.fetchExperiments()
  if (payload.data?.id) {
    selectedExpId.value = payload.data.id
    ElMessage.success(`新实验 #${payload.data.id} 已自动选中`)
  }
  
})

// 实时根据 selectedExpId 在实验列表中查找完整对象
// computed会在响应式结果发送变化的时候自动更新
const selectedExperiment = computed(() => {
  if (!selectedExpId.value || !expSelector.value?.experiments) return null
  return expSelector.value.experiments.find(
    (e: any) => e.id === selectedExpId.value
  )
})

// 最新信号数据
const latestSignal = ref<Record<string, any> | null>(null)
const signalLoading = ref(false)

// 信号辅助函数
function signalTagType(signal: number): 'success' | 'danger' | 'info' {
  if (signal === 1) return 'success'
  if (signal === -1) return 'danger'
  return 'info'
}
function signalText(signal: number): string {
  if (signal === 1) return '买入'
  if (signal === -1) return '卖出'
  return '保持(无操作)'
}

// 获取最新信号
async function fetchLatestSignal() {
  const exp = selectedExperiment.value
  if (!exp?.train_dir) {
    latestSignal.value = null
    return
  }
  signalLoading.value = true
  try {
    // 切割路径，兼容 Windows/Unix 分隔符
    const parts = exp.train_dir.split(/[\\/]/)
    if (parts.length < 3) {
      console.warn('train_dir 格式异常:', exp.train_dir)
      latestSignal.value = null
      return
    }
    const relativeDir = parts.slice(1).join('/')                // 27_AUTO_.../2.ModelData
     // 记录实验文件夹名
    signalExperimentName.value = parts[1]   // 例如 "27_AUTO_2026-06-27_16_08"
    const filePath = `${relativeDir}/latest_signal.csv`

    const res = await getFileData(filePath, DataDirType.experiment, SortOrder.desc, 1, 1)
    
    if (res.code === 0 && res.data?.data?.length > 0) {
      // FullFileData.data 是 Record<string, any>[]，直接取第一个对象
      const row = res.data.data[0]
      // 将数字类型的字段从字符串转为 number
      const parsed: Record<string, any> = {}
      for (const key of Object.keys(row)) {
        const val = row[key]
        parsed[key] = (val !== null && val !== undefined && val !== '' && !isNaN(Number(val))) 
          ? Number(val) 
          : val
      }
      latestSignal.value = parsed
    } else {
      latestSignal.value = null
    }
  } catch (err: any) {
    console.error('获取最新信号异常:', err)
    latestSignal.value = null
  } finally {
    signalLoading.value = false
  }
}

// 监听选中实验变化
watch(selectedExperiment, () => {
  fetchLatestSignal()
  console.log(selectedExperiment.value)
})



</script>