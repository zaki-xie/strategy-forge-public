import http from './http'
import type { ApiResponse } from './types'

// 获取实验列表
export const getExperiments = (limit: number = 20): Promise<ApiResponse> =>
  http.get('/experiment/list', { params: { limit } })

// 获取单个实验详情
export const getExperimentDetail = (expId: number): Promise<ApiResponse> =>
  http.get(`/experiment/${expId}`)

export const getExperimentById = (id: number): Promise<ApiResponse> => 
  http.get(`/experiment/${id}`)


export const deleteExperiment = (expId: number): Promise<ApiResponse> => 
  http.delete(`/experiment/${expId}`)
