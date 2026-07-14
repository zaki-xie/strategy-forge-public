import http from './http'
import type { ApiResponse } from './types'
// 全量更新
export const updateAllData = (): Promise<ApiResponse> => http.post('/data-collector/update')

// 工厂函数
function trigger(endpoint: string) {
  return () :Promise<ApiResponse> => http.post(`/data-collector/update/${endpoint}`)
}

export const updateAuSpot   = trigger('spot')
export const updateHuaanNav = trigger('nav')
export const update518880   = trigger('etf')
export const updateGoldApi  = trigger('goldapi')
export const updateDxy      = trigger('dxy')
export const updateDgs10    = trigger('dgs10')
export const updateUsdcny   = trigger('cny')
export const updateBrent    = trigger('brent')
export const updateSpdr     = trigger('spdr')
export const updateKline    = trigger('kline')