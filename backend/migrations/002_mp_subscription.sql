-- UniSub 迁移 002: 新增 MoviePilot 订阅子表
-- 背景: MP 订阅镜像双写功能。MP 订阅粒度按季，一个 UniSub 订阅（整剧一行）
--       可对应多条 MP 订阅，故用独立子表 mp_subscription 存储。
--       create_all 只建新表不改存量表，本表为全新表，新库由 create_all 自动建立，
--       此 SQL 供存量库手工执行。
-- 执行: psql -h 192.168.31.10 -U tgbot -d unisub -f backend/migrations/002_mp_subscription.sql
-- 对应模型: app/models/mp_subscription.py

CREATE TABLE IF NOT EXISTS mp_subscription (
    id VARCHAR(36) PRIMARY KEY,
    subscription_id VARCHAR(36) NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
    tmdb_id INTEGER NOT NULL,
    season INTEGER,                        -- 季号（电影为 NULL）
    mp_sub_id INTEGER,                     -- MoviePilot 订阅 ID
    mp_status VARCHAR(50),                 -- MP 状态: N-新建 / R-订阅中
    mp_missing_eps INTEGER DEFAULT 0,
    mp_completed_eps INTEGER DEFAULT 0,
    mp_total_eps INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);

-- 一个订阅的每一季只镜像一条 MP 订阅（电影 season 为 NULL）
CREATE UNIQUE INDEX IF NOT EXISTS ix_mp_subscription_sub_season ON mp_subscription (subscription_id, season);

-- 按 tmdb_id 反查加速
CREATE INDEX IF NOT EXISTS ix_mp_subscription_tmdb_id ON mp_subscription (tmdb_id);
