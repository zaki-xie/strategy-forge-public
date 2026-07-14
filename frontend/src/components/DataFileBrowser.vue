<template>
  <div>
    <h2>数据文件浏览</h2>
    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 15px;">
      <span>数据目录：</span>
      <el-select v-model="currentDir" @change="fetchStatus" style="width: 150px;">
        <el-option
          v-for="dir in allowedDirs"
          :key="dir"
          :label="dirLabel(dir)"
          :value="dir"
        />
      </el-select>
      <el-button @click="fetchStatus" :loading="loadingStatus">刷新状态</el-button>
    </div>

    <!-- 原始/预处理目录 -->
    <el-table :data="files" border stripe style="width: 100%" v-if="currentDir !== DataDirType.experiment">
      <el-table-column label="文件路径" width="300">
        <template #default="{ row }">
          <el-link type="primary" @click="showFullData(row.file, SortOrderEnum.off)">
            {{ row.file }}
          </el-link>
        </template>
      </el-table-column>
      <el-table-column prop="start_date" label="起始日期" width="150" />
      <el-table-column label="最新日期" width="150">
        <template #default="{ row }">
          <span
            :style="{
              color: isDateOutdated(row.latest_date) ? '#F56C6C' : '',
              fontWeight: isDateOutdated(row.latest_date) ? 'bold' : ''
            }"
          >
            {{ row.latest_date || '-' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="records" label="记录数" width="100" />
    </el-table>

    <!-- 实验目录：分组折叠面板 -->
    <!-- 实验目录下包含多个实验文件夹需要做折叠处理 -->
    <el-collapse v-else v-model="activeExperimentNames" accordion>
      <el-collapse-item
        v-for="exp in groupedExperiments"
        :key="exp.name"
        :title="`📁 ${exp.name}（${exp.files.length} 个文件）`"
        :name="exp.name"
      >
        <el-table :data="exp.files" border stripe size="small">
          <el-table-column label="文件路径" width="300">
            <template #default="{ row }">
              <el-link type="primary" @click="showFullData(row.file, SortOrderEnum.off)">
                 {{ row.file.split('/').slice(1).join('/') }}
              </el-link>
            </template>
          </el-table-column>
          <el-table-column prop="start_date" label="起始日期" width="150" />
          <el-table-column label="最新日期" width="150">
            <template #default="{ row }">
              <span
                :style="{
                  // color: isDateOutdated(row.latest_date) ? '#F56C6C' : '',
                  // fontWeight: isDateOutdated(row.latest_date) ? 'bold' : ''
                }"
              >
                {{ row.latest_date || '-' }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="records" label="记录数" width="100" />
        </el-table>
      </el-collapse-item>
    </el-collapse>

    <!-- 全量数据对话框 -->
    <el-dialog
      v-model="dataVisible"
      :title="'全量数据：' + fullFileName"
      width="90%"
      top="3vh"
      destroy-on-close
    >
      <div v-loading="dataLoading">
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px;">
          <span style="font-size: 14px; color: #606266;">排序方式：</span>
          <el-select v-model="sortOrder" @change="handleSortChange" style="width: 130px;">
            <el-option label="不排序" :value="SortOrderEnum.off" />
            <el-option label="日期正序" :value="SortOrderEnum.asc" />
            <el-option label="日期逆序" :value="SortOrderEnum.desc" />
          </el-select>
        </div>

        <el-table
          :data="fullData"
          border
          stripe
          max-height="800"
          style="width: 100%"
          v-if="fullData.length > 0"
        >
          <el-table-column
            v-for="col in fullColumns"
            :key="col"
            :prop="col"
            :label="col"
            show-overflow-tooltip
          />
        </el-table>
        
        <el-empty v-else description="暂无数据" />

        <div style="margin-top: 12px; display: flex; justify-content: flex-end;">
          <el-pagination
            v-if="totalRows > 0"
            v-model:current-page="currentPage"
            v-model:page-size="pageSize"
            :page-sizes="[20, 50, 100, 200]"
            :total="totalRows"
            layout="total, sizes, prev, pager, next, jumper"
            @current-change="handlePageChange"
            @size-change="handleSizeChange"
          />
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onActivated, computed } from 'vue'
import { getOriginalDataStatus, getFileData } from '@/api/dataView'
// import type { FullFileData } from '@/api/dataView'
import { DataDirType, SortOrder } from '@/api/types'

const SortOrderEnum = SortOrder
const activeExperimentNames = ref<string[]>([])

// Props
const props = withDefaults(
  defineProps<{
    allowedDirs?: DataDirType[]
    defaultDir?: DataDirType
  }>(),
  {
    allowedDirs: () => [DataDirType.original, DataDirType.processed, DataDirType.experiment],
    defaultDir: DataDirType.original,
  }
)

// 状态
const currentDir = ref<DataDirType>(props.defaultDir)
const files = ref<Array<{ file: string; start_date: string; latest_date: string; records: number }>>([])
const loadingStatus = ref(false)

async function fetchStatus() {
  loadingStatus.value = true
  try {
    const res = await getOriginalDataStatus(currentDir.value)
    files.value = res.data.files
  } catch (err) {
    console.error('获取数据状态失败', err)
  } finally {
    loadingStatus.value = false
  }
}

// 目录标签
function dirLabel(dir: DataDirType): string {
  const labels: Record<DataDirType, string> = {
    [DataDirType.original]: '原始数据',
    [DataDirType.processed]: '预处理数据',
    [DataDirType.experiment]: '实验数据'
  }
  return labels[dir] || dir
}

// 全量对话框
const dataVisible = ref(false)
const dataLoading = ref(false)
const fullData = ref<Record<string, any>[]>([])
const fullFileName = ref('')
const fullColumns = ref<string[]>([])
const sortOrder = ref<SortOrder>(SortOrder.off)
const currentPage = ref(1)
const pageSize = ref(50)
const totalRows = ref(0)

async function showFullData(file: string, sort: SortOrder = SortOrder.off, page: number = 1) {
  dataVisible.value = true
  dataLoading.value = true
  fullFileName.value = file
  currentPage.value = page
  try {
    const res = await getFileData(file, currentDir.value, sort, page, pageSize.value)
    fullColumns.value = res.data.columns
    fullData.value = res.data.data
    totalRows.value = res.data.total
  } catch (err) {
    console.error('获取全量数据失败', err)
    fullData.value = []
  } finally {
    dataLoading.value = false
  }
}

function handleSortChange(val: SortOrder) {
  if (fullFileName.value) {
    sortOrder.value = val
    showFullData(fullFileName.value, val, 1)
  }
}

function handlePageChange(page: number) {
  if (fullFileName.value) {
    showFullData(fullFileName.value, sortOrder.value, page)
  }
}

function handleSizeChange(size: number) {
  pageSize.value = size
  if (fullFileName.value) {
    showFullData(fullFileName.value, sortOrder.value, 1)
  }
}

// 获取本周五的日期字符串（YYYY-MM-DD）
function getThisFriday(): string {
  const now = new Date()
  // 获取今天是周几
  const dayOfWeek = now.getDay() // 0=周日, 1=周一, ..., 6=周六
  let diff = 5 - dayOfWeek  //今天离周五差几天
  if (dayOfWeek === 6) diff = -1   // 周六 → 昨天是周五
  if (dayOfWeek === 0) diff = -2   // 周日 → 前天是周五
  const friday = new Date(now)
  friday.setDate(now.getDate() + diff)  // 设置时间到周五
  return friday.toISOString().slice(0, 10)  // 截取返回日期部分的字符串
}

// 若日期小于周五返回false，否则返回true
function isDateOutdated(latestDate: string | null | undefined): boolean {
  if (!latestDate) return true   // 无数据视为滞后
  const targetFriday = getThisFriday()
  return latestDate < targetFriday
}

interface GroupedExperiment {
  name: string  // 标记实验名字
  files: Array<{ file: string; start_date: string; latest_date: string; records: number }> //后端返回的files结构
}

// 从json字段files中提取出每个实验的名字，并按名字分类存放对应文件
const groupedExperiments = computed<GroupedExperiment[]>(() => {
  if (currentDir.value !== DataDirType.experiment) return []
  const map = new Map<string, GroupedExperiment>()
  files.value.forEach(file => {         // 遍历json中的files字段
    const parts = file.file.split('/')  // 分割提取文件夹名
    if (parts.length > 0) {
      const expName = parts[0]          // 第一个文件夹名为实验名，为一个分类
      if (!map.has(expName)) {          // map中还未添加该实验名，则将其添加为一个分类
        map.set(expName, { name: expName, files: [] })
      }
      map.get(expName)!.files.push(file)  // 将该段file内容添加到对应分类
    }
  })
  return Array.from(map.values())
})

onMounted(() => {

})

// 组件被缓存在 keep-alive 中，每次切回时重新加载数据
onActivated(() => {
  fetchStatus()
})
</script>