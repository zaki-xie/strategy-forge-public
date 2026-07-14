import http from './http'
import { DataDirType, SortOrder } from './types'
import type { ApiResponse } from './types'

export interface FileStatus {
  file: string
  start_date: string
  latest_date: string
  records: number
}

export interface FullFileData {
  filename: string
  columns: string[]
  total: number          // 总行数
  page: number           // 当前页
  page_size: number      // 每页条数
  data: Record<string, any>[]
  sort_applied?: { column: string; order: string }
}

export const getOriginalDataStatus = (
  dirType: DataDirType = DataDirType.original
): Promise<ApiResponse<{ files: FileStatus[] }>> =>
  http.get('/data-view/status', { params: { dir_type: dirType } })



export const getFileData = (
  filename: string,
  dirType: DataDirType = DataDirType.original,
  sortDate: SortOrder = SortOrder.off,
  page: number = 1,
  pageSize: number = 50
): Promise<ApiResponse<FullFileData>> =>
  http.get('/data-view/data/' + encodeURIComponent(filename), {
    params: {
      sort_date: sortDate,
      page,
      page_size: pageSize,
      dir_type: dirType,
    },
  })

export interface GoldPriceData {
  dates: string[]
  series: Record<string, (number | null)[]>
}

export const getGoldPrices = (freq = 'D'): Promise<ApiResponse<GoldPriceData>> => {
  return http.get('/data-view/gold-prices', { params: { freq } })
}


export interface TradeSignal {
  buy: { date: string; price: number }[]
  sell: { date: string; price: number }[]
}

export interface LatestSnapshot {
  date: string
  signal: number
  current_position: string
  position_value: number
  strategy_nav: number
  benchmark_nav: number
}

export interface Spilt_train_params {
  split_ratio: number
  ols_window: number
  zscore_window: number
  buy_threshold: number
  sell_threshold: number
  split_cutoff_date: string
}

export interface BacktestEquityData {
  dates: string[]
  strategy_nav: number[]
  benchmark_nav: number[]
  strategy_dd: number[]
  benchmark_dd: number[]
  performance: {
    strategy_total_return: string
    benchmark_total_return: string
    strategy_sharpe: number | null
    benchmark_sharpe: number | null
    strategy_max_dd: string
    benchmark_max_dd: string
  }
  buy_count: number
  sell_count: number
  avg_hold_days: number | null
  trade_signals: TradeSignal
  latest_snapshot: LatestSnapshot
  spilt_train_params: Spilt_train_params
}

export const getBacktestData = (expId: number): Promise<ApiResponse<BacktestEquityData>> =>
  http.get(`/data-view/${expId}/backtest-data`)


export interface RealtimeEquityData {
  dates: string[]
  nav_real: number[]
  cash: number[]
  shares: number[]
  total_asset: number[]
  drawdown: number[]
  benchmark_nav: number[]          // 基准净值曲线
  benchmark_total_asset: number[]  // 基准总资产曲线
  benchmark_drawdown: number[]           // 基准回撤曲线
  performance: {
    final_total?: number
    final_nav?: number
    annual_return?: string
    sharpe?: number
    max_drawdown?: string
    fee_total?: number
    
    benchmark_final_total?: number
    benchmark_annual_return?: number
    benchmark_sharpe?: number
    benchmark_max_drawdown?: number
    benchmark_nav_end?: number

    backtest_strategy_nav_end?: number
    backtest_benchmark_nav_end?: number

  }
  trade_stats: {
    buy_count?: number
    sell_count?: number
    total_trades?: number
    avg_hold_days?: number
    total_fee?: number
    signal_distribution?: Record<string, number>
  }
  max_drawdown_info: {
    start_date?: string
    end_date?: string
    drawdown?: string
  }
  current_account: {
    date?: string
    cash?: number
    shares?: number
    total_asset?: number
    nav_real?: number
    position?: string
  }
  recent_trades: Array<{
    buy_date?: string
    buy_price?: number
    sell_date?: string | null
    sell_price?: number | null
    hold_days?: number | null
  }>
  buy_signals: Array<{ date: string; price: number }>
  sell_signals: Array<{ date: string; price: number }>
  fund_nav?: {
    dates: string[]
    values: number[]
  }
}

export const getRealtimeData = (expId: number): Promise<ApiResponse<RealtimeEquityData>> =>
  http.get(`/data-view/${expId}/realtime-data`)