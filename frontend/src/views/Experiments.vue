<template>
  <div style="padding: 20px;">
    <h2>实验数据总览</h2>
    <el-button @click="loadExperiments" :loading="loading" style="margin-bottom: 16px;">
      刷新数据
    </el-button>

    <el-table
      :data="paginatedData"
      border
      stripe
      style="width: 100%"
      :default-sort="{ prop: 'id', order: 'descending' }"
      @sort-change="handleSortChange"
      max-height="600"
    >
      <el-table-column prop="id" label="ID" width="60" sortable="custom" />
      <el-table-column prop="experiment_name" label="名称" min-width="160" show-overflow-tooltip />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small">
            {{ statusText(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="180" sortable="custom" />
      <el-table-column label="样本数" width="120">
        <template #default="{ row }">
          <span v-if="row.split_train_samples">
            {{ row.split_train_samples }} / {{ row.split_test_samples }}
          </span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="训练参数" width="140">
        <template #default="{ row }">
          <span v-if="row.train_ols_window">
            窗口{{ row.train_ols_window }}周<br />阈值{{ row.train_buy_threshold }}/{{ row.train_sell_threshold }}
          </span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <!-- 回测绩效 -->
      <el-table-column label="回测夏普" width="90">
        <template #default="{ row }">
          <span v-if="row.backtest_performance_json?.strategy_sharpe">
            {{ row.backtest_performance_json.strategy_sharpe }}
          </span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="回测最大回撤" width="110">
        <template #default="{ row }">
          <span v-if="row.backtest_performance_json?.strategy_max_drawdown">
            {{ row.backtest_performance_json.strategy_max_drawdown }}
          </span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <!-- 实盘绩效 -->
      <el-table-column label="实盘最终净值" width="120">
        <template #default="{ row }">
          <span v-if="row.realtime_performance_json?.final_nav">
            {{ row.realtime_performance_json.final_nav }}
          </span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="实盘年化收益" width="110">
        <template #default="{ row }">
          <span v-if="row.realtime_performance_json?.annual_return">
            {{ row.realtime_performance_json.annual_return }}
          </span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="实盘夏普" width="90">
        <template #default="{ row }">
          <span v-if="row.realtime_performance_json?.sharpe">
            {{ row.realtime_performance_json.sharpe }}
          </span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="实盘最大回撤" width="120">
        <template #default="{ row }">
          <span v-if="row.realtime_performance_json?.max_drawdown">
            {{ row.realtime_performance_json.max_drawdown }}
          </span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="实盘手续费" width="100">
        <template #default="{ row }">
          <span v-if="row.realtime_performance_json?.fee_total">
            {{ row.realtime_performance_json.fee_total }}
          </span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="实盘vs回测差值" width="140">
        <template #default="{ row }">
          <span v-if="row.realtime_performance_json?.diff_vs_strategy">
            {{ row.realtime_performance_json.diff_vs_strategy }}
          </span>
          <span v-else>-</span>
        </template>
      </el-table-column>

      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="showDetail(row)">
            详情
          </el-button>
          <el-popconfirm
            width = "200"
            title="确定删除该实验吗？此操作不可恢复！"
            confirm-button-text="删除"
            cancel-button-text="取消"
            @confirm="handleDelete(row.id)"
          >
            <template #reference>
              <el-button size="small" type="danger" link>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
      
    </el-table>

    <!-- 分页 -->
    <el-pagination
      v-model:current-page="currentPage"
      v-model:page-size="pageSize"
      :page-sizes="[10, 20, 50, 100]"
      :total="experiments.length"
      layout="total, sizes, prev, pager, next, jumper"
      style="margin-top: 16px; justify-content: flex-end;"
    />


   <!-- 详情对话框组件 -->
    <ExperimentDetailDialog
      v-model:visible="detailDialogVisible"
      :experiment="currentDetailRow"
    />
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'Experiments' })
import { ref, computed, onMounted, onActivated } from 'vue'
import { getExperiments, getExperimentById, deleteExperiment  } from '@/api/experiment'
import ExperimentDetailDialog from '@/components/ExperimentDetailDialog.vue'
import { ElMessage } from 'element-plus'

interface Experiment {
  id: number
  experiment_name: string
  status: string
  created_at: string
  updated_at?: string
  split_train_samples?: number
  split_test_samples?: number
  train_ols_window?: number
  train_buy_threshold?: number
  train_sell_threshold?: number
  backtest_performance_json?: {
    strategy_sharpe?: string
    strategy_max_drawdown?: string
  }
  realtime_performance_json?: {
    final_nav?: number
    annual_return?: string
    sharpe?: number
    max_drawdown?: string
    fee_total?: number
    diff_vs_strategy?: string
  }
}

const experiments = ref<Experiment[]>([])
const loading = ref(false)
const currentPage = ref(1)
const pageSize = ref(20)
const sortProp = ref<string>('id')
const sortOrder = ref<string>('descending')

// 前端排序
const sortedData = computed(() => {
  const list = [...experiments.value]
  if (!sortProp.value) return list
  list.sort((a, b) => {
    const aVal = a[sortProp.value as keyof Experiment]
    const bVal = b[sortProp.value as keyof Experiment]
    if (aVal == null || bVal == null) return 0
    if (typeof aVal === 'number' && typeof bVal === 'number') {
      return sortOrder.value === 'ascending' ? aVal - bVal : bVal - aVal
    }
    const strA = String(aVal)
    const strB = String(bVal)
    return sortOrder.value === 'ascending' ? strA.localeCompare(strB) : strB.localeCompare(strA)
  })
  return list
})

// 分页
const paginatedData = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return sortedData.value.slice(start, start + pageSize.value)
})

function handleSortChange({ prop, order }: any) {
  sortProp.value = prop
  sortOrder.value = order || 'descending'
}

async function loadExperiments() {
  loading.value = true
  try {
    const res = await getExperiments()
    experiments.value = res.data.experiments || []
  } catch (err) {
    console.error('加载实验列表失败', err)
  } finally {
    loading.value = false
  }
}

// 状态文本与标签类型
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
    realtimed: 'success',
  }
  return map[status] || 'info'
}

const detailDialogVisible = ref(false)
const currentDetailRow = ref<Record<string, any> | null>(null)
const detailLoading = ref(false)

async function showDetail(row: Record<string, any>) {
  //直接用现有表格数据显示
  // currentDetailRow.value = row
  // detailDialogVisible.value = true

  //调用detail接口查询显示
  detailLoading.value = true
    try {
      const res = await getExperimentById(row.id)
      const exp = res.data?.data ?? res.data   // 根据实际响应结构调整
      if (exp) {
        currentDetailRow.value = exp
        detailDialogVisible.value = true
      } else {
        ElMessage.error('获取实验详情失败')
      }
    } catch (err: any) {
      ElMessage.error(err?.response?.data?.message || '获取详情失败')
    } finally {
      detailLoading.value = false
    }
}

async function handleDelete(id: number) {
  try {
    await deleteExperiment(id)
    ElMessage.success(`实验 #${id} 已删除`)
    await loadExperiments()  // 刷新列表
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.message || '删除失败')
  }
}

onMounted(() => {

})

// 组件被缓存在 keep-alive 中，每次切回时重新加载数据
onActivated(() => {
  loadExperiments()
})
</script>