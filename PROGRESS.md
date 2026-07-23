# 任务: 自动订阅全量修复（参考 AWBotNest 原项目）

## 目标
对比 AWBotNest 原项目，修复/改进自动订阅模块的 7 个问题点。

## 步骤
- [x] 1. 前端 defaults.ts 移除抖音/快手/西瓜，补「全网」+ 完整媒体类型
- [x] 2. 后端 router 同步移除抖音/快手/西瓜，补全
- [x] 3. models.py: 补序列化、源 ID 字段、make_history_key、Filters/RunResult
- [x] 4. base.py: 新建基类 + @register 注册表
- [x] 5. nextfind.py: 加 AuthError + trust_env=False
- [x] 6. maoyan.py: 类转换 + 全网 + 媒体类型 + [:num] + Cookie
- [x] 7. douban.py: 类转换
- [x] 8. mikan.py: 类转换
- [x] 9. pipeline.py: 注册表替换 + AuthError 中止 + 去重改 tmdb_id + 终态语义
- [x] 10. lint/verify/commit

## 风险/注意
- pipeline.py 改动最大，需仔细验证逻辑
- 源文件类转换后需确认调用路径兼容
- 猫眼 Cookie 为 best-effort，不影响现有功能
