// 后端统一返回格式
export interface ApiResponse<T = any> {
  code: number
  message: string
  data: T
}

export const DataDirType = {
  original: 'original',
  processed: 'processed',
  experiment: 'experiment'
} as const
// typeof DataDirType：获取上面那个对象的类型（即 { readonly original: "original"; ... }）。
// keyof typeof DataDirType：获取该对象的所有键的联合类型，即"original" | "processed" | "weekly"
// (typeof DataDirType)[keyof typeof DataDirType]：通过键的联合索引取值，得到所有属性的值的联合类型，即 "original" | "processed" | "weekly"。
// 简单来说此处保存所有值数据，
// 同时JavaScript/TypeScript 中 值空间（变量）与 类型空间（类型）是分离的，所以同名不会冲突。
export type DataDirType = (typeof DataDirType)[keyof typeof DataDirType]

export const SortOrder = {
  off: 'off',
  asc: 'asc',
  desc: 'desc',
} as const
export type SortOrder = (typeof SortOrder)[keyof typeof SortOrder]