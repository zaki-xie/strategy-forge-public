import http from './http'
import type { ApiResponse } from './types'

// 触发数据预处理
export const runPreprocessing = (): Promise<ApiResponse> => http.post('/strategy/preprocess')

// 1. 修改 API 函数，按需发送 exp_id
export const runWeeklyAggregate = (expId?: number): Promise<ApiResponse> => {
  if (expId !== undefined) {
    return http.post('/strategy/weekly-aggregate', null, { params: { exp_id: expId } })
  }
  return http.post('/strategy/weekly-aggregate')
}
// 分割、训练、回测都需要 exp_id（必填）
export const runSplitData = (expId: number, splitRatio: number = 0.7): Promise<ApiResponse> =>
  http.post('/strategy/split-data', null, { params: { exp_id: expId, split_ratio: splitRatio } })

export const runTrainOLS = (expId: number): Promise<ApiResponse> =>
  http.post('/strategy/train-ols', null, { params: { exp_id: expId } })

export const runBacktest = (expId: number): Promise<ApiResponse> =>
  http.post('/strategy/backtest', null, { params: { exp_id: expId } })

export const runRealtime = (expId: number, initial_cash: number = 10000, min_hold_days: number = 7): Promise<ApiResponse> =>
  http.post('/strategy/realtime', null, { params: { exp_id: expId, initial_cash: initial_cash , min_hold_days: min_hold_days} })