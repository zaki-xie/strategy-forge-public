<template>
  <div>
    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
      <span>当前实验：</span>
      <el-button @click="fetchExperiments" :loading="loading">刷新列表</el-button>
    </div>

    <el-table
      ref="tableRef"
      :data="experiments"
      highlight-current-row
      :current-row="currentRow"
      @current-change="handleCurrentChange"
      style="width: 100%; max-height: 400px; overflow-y: auto;"
      border
      stripe
    >
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="experiment_name" label="名称" min-width="180" show-overflow-tooltip />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small">
            {{ statusText(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="weekly_dir" label="周频数据来源" width="400" />
      <el-table-column prop="created_at" label="创建时间" width="200" />
      <el-table-column label="样本数" width="120">
        <template #default="{ row }">
          <span v-if="row.split_train_samples">
            {{ row.split_train_samples }} / {{ row.split_test_samples }}
          </span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="回测夏普" width="100">
        <template #default="{ row }">
          <span v-if="row.backtest_performance_json?.strategy_sharpe">
            {{ row.backtest_performance_json.strategy_sharpe }}
          </span>
          <span v-else>-</span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, nextTick, onActivated } from 'vue'
import { getExperiments } from '@/api/experiment'

const props = defineProps<{
  modelValue?: number | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: number | null): void
}>()

const experiments = ref<any[]>([])
const loading = ref(false)
const currentRow = ref<any>(null)
const tableRef = ref<any>(null)   // 修复处：改为 any 类型

function setCurrentRowById(id: number | null | undefined) {
  if (id == null) {
    tableRef.value?.setCurrentRow()
    currentRow.value = null
    return
  }
  const found = experiments.value.find(exp => exp.id === id)
  if (found) {
    tableRef.value?.setCurrentRow(found)
    currentRow.value = found
  } else {
    tableRef.value?.setCurrentRow()
    currentRow.value = null
  }
}

watch(() => props.modelValue, (newVal) => {
  nextTick(() => setCurrentRowById(newVal))
  console.log('at experimentselector selectedExpId 已更新为:', props.modelValue)
}, { immediate: true })

async function fetchExperiments() {
  loading.value = true
  try {
    const res = await getExperiments()
    experiments.value = res.data.experiments || []
    await nextTick()
    setCurrentRowById(props.modelValue)
  } catch (err) {
    console.error('获取实验列表失败', err)
  } finally {
    loading.value = false
  }
}

function handleCurrentChange(row: any) {
  currentRow.value = row
  emit('update:modelValue', row ? row.id : null)
}

function statusText(status: string) {
  const map: Record<string, string> = {
    weekly_aggregator: '已聚合',
    splitted: '已分割',
    trained: '已训练',
    backtested: '已回测',
    realtimed: '已实盘',
  }
  return map[status] || status || '未开始'
}

function statusTagType(status: string) {
  const map: Record<string, string> = {
    weekly_aggregator: 'info',
    splitted: 'warning',
    trained: 'primary',
    backtested: 'primary',
    realtimed: 'success'
  }
  return map[status] || 'info'
}

onMounted(() => {

})

// 组件被缓存在 keep-alive 中，每次切回时重新加载数据
onActivated(() => {
  fetchExperiments()
})

defineExpose({ fetchExperiments, experiments })
</script>