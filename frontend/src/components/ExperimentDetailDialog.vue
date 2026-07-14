<template>
  <el-dialog
    :model-value="visible"
    @update:model-value="$emit('update:visible', $event)"
    title="实验详情"
    width="850px"
    top="5vh"
    destroy-on-close
  >
    <template v-if="experiment">
      <el-descriptions :column="2" border>
        <template v-for="(value, key) in experiment" :key="key">
          <el-descriptions-item :label="formatLabel(key)" :span="getFieldSpan(key, value)">
            <!-- 对象或数组用折叠面板展示 JSON -->
            <template v-if="isObject(value)">
              <el-collapse>
                <el-collapse-item :title="formatLabel(key)">
                  <pre style="max-height: 200px; overflow: auto; font-size: 12px; margin: 0;">{{ JSON.stringify(value, null, 2) }}</pre>
                </el-collapse-item>
              </el-collapse>
            </template>
            <!-- 普通值 -->
            <template v-else>
              {{ value ?? '-' }}
            </template>
          </el-descriptions-item>
        </template>
      </el-descriptions>
    </template>
    <template #footer>
      <el-button @click="$emit('update:visible', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { toRefs } from 'vue'

const props = defineProps<{
  visible: boolean
  experiment?: Record<string, any> | null
}>()

defineEmits<{
  (e: 'update:visible', value: boolean): void
}>()

const { experiment } = toRefs(props)

// 判断值是否为对象（包括数组），排除 null
function isObject(value: any): boolean {
  return value !== null && typeof value === 'object'
}

// 字段标签映射
function formatLabel(key: string): string {
  const map: Record<string, string> = {
    id: 'ID',
    experiment_name: '实验名称',
    status: '状态',
    created_at: '创建时间',
    updated_at: '更新时间',
    split_ratio: '分割比例',
    split_factor_cols: '因子列',
    split_y_col: '目标列',
    split_train_samples: '训练样本数',
    split_test_samples: '测试样本数',
    split_train_date_start: '训练集开始日期',
    split_train_date_end: '训练集结束日期',
    split_test_date_start: '测试集开始日期',
    split_test_date_end: '测试集结束日期',
    split_cutoff_date: '数据分割日期',
    train_ols_window: 'OLS窗口',
    train_zscore_window: 'Z-Score窗口',
    train_buy_threshold: '买入阈值',
    train_sell_threshold: '卖出阈值',
    train_ols_train_samples: '实际训练样本数',
    train_ols_test_samples: '实际测试样本数',
    backtest_performance_json: '回测绩效',
    backtest_trade_signals: '回测交易信号',
    backtest_latest_snapshot: '回测最后快照',
    backtest_buy_count: '回测买入次数',
    backtest_sell_count: '回测卖出次数',
    backtest_avg_hold_days: '回测平均持仓天数',
    realtime_performance_json: '实盘绩效',
    realtime_trade_stats_json: '实盘交易统计',
    realtime_max_drawdown_json: '实盘最大回撤',
    realtime_current_account_json: '实盘当前账户',
    realtime_recent_trades_json: '实盘最近交易',
    weekly_dir: '周频数据路径',
    split_dir: '分割数据路径',
    train_dir: '训练数据路径',
    train_model_dir: '训练模型路径',
    backtest_dir: '回测数据路径',
    realtime_dir: '实盘数据路径',
    output_dir: '输出根目录',
    notes: '备注',
  }
  return map[key] || key
}

// 用于为json数据配置占用两列
function getFieldSpan(key: string, value: any): number {
  return isObject(value) ? 2 : 1
}
</script>