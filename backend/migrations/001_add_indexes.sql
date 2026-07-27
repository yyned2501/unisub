-- UniSub 迁移 001: 补建模型新增索引
-- 背景: models 中新增了 __table_args__ 索引，但 create_all 不会为已存在的表补索引，
--       项目暂未引入 alembic，手工 SQL 归档于此，供存量库执行。
-- 执行: psql -h 192.168.31.10 -U unisub -d unisub -f backend/migrations/001_add_indexes.sql
-- 对应模型: app/models/activity_log.py, app/models/subscription.py

-- 活动日志按时间倒序查询加速
CREATE INDEX IF NOT EXISTS ix_activity_logs_created_at ON activity_logs (created_at);

-- 订阅列表「未完成 + 未拉黑」过滤加速
CREATE INDEX IF NOT EXISTS ix_subscriptions_completed_blacklisted ON subscriptions (completed, blacklisted);

-- tmdb_id 全局唯一（与 add_subscription 的查重逻辑一致；执行前需确认无重复数据）
CREATE UNIQUE INDEX IF NOT EXISTS ix_subscriptions_tmdb_id ON subscriptions (tmdb_id);
