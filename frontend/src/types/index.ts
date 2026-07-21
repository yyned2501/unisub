/**
 * 领域类型统一出口。
 *
 * 约定：
 * - 本目录类型镜像后端 Pydantic schemas（backend/app/schemas/）与 router 响应。
 * - 字段名保持 snake_case 与后端一致；后端 datetime 对应 TS string（ISO）。
 * - 修改后端 schema 时同步更新此处。
 */
export * from './common'
export * from './auth'
export * from './subscription'
export * from './platform'
export * from './dashboard'
export * from './search'
export * from './emby'
export * from './cd2'
export * from './auto-subscribe'
export * from './task'
export * from './log'
