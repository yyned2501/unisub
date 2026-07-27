-- UniSub 迁移 003: 新增 TMDB 季集缓存表
-- 背景: MP 订阅计算缺集季需要 seasons（按季集数）数据。此前每次同步都调
--       MP media 接口获取，改为本地缓存：扫库/自动订阅调 TMDB 详情时顺手写入，
--       订阅同步直接读本地，大幅减少对 MP 的调用。
--       本表为全新表，新库由 create_all 自动建立，此 SQL 供存量库手工执行。
-- 执行: psql -h 192.168.31.10 -U tgbot -d unisub -f backend/migrations/003_tmdb_season.sql
-- 对应模型: app/models/tmdb_season.py

CREATE TABLE IF NOT EXISTS tmdb_season (
    tmdb_id INTEGER NOT NULL,
    season INTEGER NOT NULL,                 -- 季号（不含特典季 0）
    episode_count INTEGER DEFAULT 0,
    air_date VARCHAR(20),
    updated_at TIMESTAMPTZ,
    PRIMARY KEY (tmdb_id, season)
);
