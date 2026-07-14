# 任务: UI 重构 (Element Plus → Naive UI) + 后端增强

## 目标
将前端从 Element Plus 迁移到 Naive UI，同时重构 API 层为 service 架构；后端增强包括 Emby 集成、NextFind 更多 API 方法、双向同步。

## 步骤

### 后端 (已完成)
- [x] Emby 服务: `backend/app/services/emby.py` — 连接测试 + 信息查询
- [x] NextFind 增强: 资源搜索、探针解包、HDHive 解锁、补缺集等新 API 方法
- [x] NextFind 管理 API: `backend/app/services/nextfind_admin.py` — Web API 登录 + 缺失集查询
- [x] 搜索增强: poster URL 解析、type 类型映射 (`movie` → `电影`)
- [x] 平台路由: 增加 Emby 连接测试
- [x] 仪表盘路由: 增加 Emby 状态检测
- [x] 编排器: 重写为双向同步 (NF→US + US→NF + 状态更新)
- [x] schema: SubscriptionSyncResult 增加 action/nf_subscribed 字段

### 前端 (部分完成)
- [x] 依赖迁移: package.json 添加 Naive UI + pinia，删除 element-plus
- [x] 新目录结构创建:
  - [x] `store/modules/` — Pinia stores
  - [x] `service/` — API service 层 (axios 封装)
  - [x] `plugins/` — 插件注册
  - [x] `components/common/` — 公共组件 (app-provider)
  - [x] `views/settings/` — 设置页子视图 (PlatformSettings, TaskSettings)
- [x] App.vue — 从 Element Plus 布局 改为 Naive UI + Pinia 架构
- [x] main.js — 从 Element Plus 注册改为 Naive UI + Pinia 初始化
- [x] router/index.js — 路由重构 (settings 改为子路由)
- [ ] 删除了旧的 api/ 和 stores/ 文件，但新 service 层可能未完全实现所有接口
- [ ] 各视图组件 (DashboardView, SearchView, SubscriptionsView) — 疑似未完成 Naive UI 组件替换
- [ ] 样式系统: `styles/` 目录 + `uno.config.ts` — 可能需要调整

### 风险/注意
- package-lock.json 已大改 (4019 行)，确保 `npm install` 通过
- 删除的旧文件 (api/, stores/, SettingsView.vue) 需要确认无遗留引用
- Naive UI 表格/表单组件使用方式与 Element Plus 差异较大，视图组件需逐个适配
- 新增 `frontend/public/` 目录为空，需确认是否需要静态资源