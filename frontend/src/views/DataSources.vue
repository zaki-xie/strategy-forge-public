<template>
  <div style="padding: 20px;">
    <h2>数据采集控制</h2>

    <!-- 全量更新 -->
    <el-button
      type="primary"
      @click="triggerUpdate(updateAllData, '全量更新')"
      style="margin-bottom: 15px;"
    >
      一键更新所有数据
    </el-button>

    <!-- 单独更新（分组排列） -->
    <el-row :gutter="10">
      <el-col
        v-for="item in [
          { fn: updateAuSpot,   label: 'Au99.99 现货' },
          { fn: updateHuaanNav, label: '000217 净值' },
          { fn: update518880,   label: '518880 行情' },
          { fn: updateGoldApi,  label: '国际金价' },
          { fn: updateDxy,      label: '美元指数' },
          { fn: updateDgs10,    label: '美债利率' },
          { fn: updateUsdcny,   label: '人民币汇率' },
          { fn: updateBrent,    label: '布伦特原油' },
          { fn: updateSpdr,     label: 'SPDR 持仓' },
          { fn: updateKline,    label: '分钟K线' },
        ]"
        :key="item.label"
        :span="8"
      >
        <el-button
          @click="triggerUpdate(item.fn, item.label)"
          style="width: 100%; margin-bottom: 10px;"
        >
          {{ item.label }}
        </el-button>
      </el-col>
    </el-row>

    <el-divider />
    <!-- 数据浏览：允许所有目录 -->
    <DataFileBrowser
      :allowedDirs="[DataDirTypeEnum.original, DataDirTypeEnum.processed, DataDirTypeEnum.experiment]"
      :defaultDir="DataDirTypeEnum.original"
    />
   
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'DataSources' })
import {
  updateAllData,
  updateAuSpot,
  updateHuaanNav,
  update518880,
  updateGoldApi,
  updateDxy,
  updateDgs10,
  updateUsdcny,
  updateBrent,
  updateSpdr,
  updateKline,
} from '@/api/dataCollector'

// 导入数据查看相关函数
import { ElMessage } from 'element-plus'
import type { ApiResponse } from '@/api/types'
import { DataDirType } from '@/api/types'
import DataFileBrowser from '@/components/DataFileBrowser.vue'

const DataDirTypeEnum = DataDirType


// 每个按钮的触发函数
async function triggerUpdate(fn: () => Promise<ApiResponse>, label: string) {
  try {
    const res = await fn()
    ElMessage({ message: res.message || `${label} 任务已启动`, type: 'success' })
  } catch (err: any) {
    ElMessage({ message: err.message || `${label} 请求失败`, type: 'error' })
  }
}

</script>
