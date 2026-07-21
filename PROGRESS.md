# 任务: 自动订阅参考归档 + Netflix 自动订阅修复

## 目标
归档两个外部自动订阅插件，并修复 Netflix 抓取错误、类别兼容、真实 Cron 调度及 NextFind 假成功问题。

## 步骤
- [ ] 导入参考插件快照及来源说明
- [ ] 重构自动订阅服务边界与配置/历史存储
- [ ] 修复 Netflix 抓取、类别迁移和错误可见性
- [ ] 接入 Cron 调度并防止并发重复运行
- [ ] 严格校验 NextFind 创建订阅结果
- [ ] 更新自动订阅页面并完成构建/接口验证

## 风险/注意
- 工作树已有大量未提交改动；只修改自动订阅相关文件，避免覆盖无关内容。
- 自动订阅运行时 JSON 数据必须通过 Docker 卷持久化。
- 参考插件仅用于比对，不作为 UniSub 的运行时依赖。

---

# 任务: TMDB 定时扫描 + 手动扫描按钮 + 进度展示

## 目标
为 Emby 缺集分析页添加一键全量扫描功能（sync-cache → update-tmdb-all → sync-subscriptions），
带进度条展示、运行时锁定、以及后台定时自动扫描。

## 步骤

### 后端
- [x] `EmbyService.update_tmdb_data_all()` — 扫描 emby_cache 所有记录（不限已订阅），带进度回调
- [x] `EmbyService.update_tmdb_data_missing()` — 轻量补充，只处理 tmdb_total_eps 为 NULL 的记录
- [x] `EmbyScanService.run_light_scan()` — 快速刷新两步：sync-cache + 补充缺失 TMDB，用于 10 分钟定时
- [x] `EmbyScanService` — 一键扫描封装、内存进度跟踪（三步：0-30%-80%-100%）
- [x] `POST /api/emby/scan` — 手动触发全量扫描，运行时返回 409
- [x] `GET /api/emby/scan-status` — 实时查询扫描进度
- [x] `backend/app/services/scheduler.py` — 后台调度循环，支持双层次：
  - 轻量刷新（默认 10 分钟）：sync-cache → 补充缺失 TMDB
  - 全量扫描（默认 60 分钟）：sync-cache → 全量 TMDB → 同步订阅
- [x] `main.py` lifespan — 同时启动轻量刷新和全量扫描两个 runner
- [x] `tasks.py` 新增 `light_interval_minutes` 配置项

### 前端
- [x] `frontend/src/service/api/emby.js` — 新增 `triggerEmbyScan()` + `getEmbyScanStatus()`
- [x] `EmbyAnalysis.vue` — 新增「TMDB 全量扫描」按钮、进度条、1.5s 轮询、组件卸载清理

### 风险/注意
- 后台扫描需独立 DB session（asyncio.create_task 中创建），不依赖请求 session
- 调度器每 10 秒检查配置
- 轻量扫描使用独立进度字段，与全量扫描共享 `running` 锁防冲突
- `update_tmdb_data_missing` 并发 3 个 TMDB 查询，批间间隔 0.3s，不重复查询已有数据

## 追加任务：CD2 设置

### 目标
在设置中提供独立 CD2 配置页，保存 URL、API Key 和无效媒体目录的移动目标位置。

### 步骤
- [x] 新增 CD2 独立配置模型、schema、service 和 API
- [x] 新增 CD2 设置页面、路由和菜单入口
- [x] 完成前后端验证与部署

## 追加任务：无 TMDB 媒体列表 + CD2 移动

### 目标
在前端展示 Emby 中有但 TMDB 无对应数据的媒体列表，支持一键 CD2 移动到待整理目录。

### 步骤
- [x] EmbyCache 加 emby_path 字段 + 同步时写入
- [x] 后端 list_tmdb_404_items + 移动 API
- [x] CD2 gRPC 客户端加 move_file / ensure_directory
- [x] 前端 API、composable、Tmdb404View 页面、路由、菜单
- [x] 部署验证

### 风险/注意
- 生产数据库需要手动 ADD COLUMN emby_path（已执行）
- 路径前缀映射 `/mnt/user/clouddrive/CloudDrive/` → `/` 和 `/media/Symedia/MoviePilot/` → 直接原样传递

### 风险/注意
- CD2 gRPC-Web 方法签名尚未由项目内 proto 或客户端代码确认，本步骤只持久化配置，不实现虚假的连接测试或移动调用。
- 使用独立配置表，避免修改现有 `platform_configs` 表造成生产数据库字段迁移问题。