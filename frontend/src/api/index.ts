import http from './http'

// 根接口
export const getRoot = (): 
    Promise<{ status: string }> =>
        http.get('/')

// 数据更新
// export const updateAllData = () => http.post('/data/update/all')

// 以后添加其他接口
// export const getWeeklyData = (date: string) => http.get('/data/weekly', { params: { date } })