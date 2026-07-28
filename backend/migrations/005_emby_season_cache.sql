-- UniSub 迁移 005: 新增 Emby 按季库集数缓存表
-- 背景: MP 镜像订阅原先每轮都调 MP notexists 实时比对 Emby 库算缺集，频繁打 Emby、
--       慢且易 502/超时。改为本地计算：定期 Emby 同步（sync_cache）批量拉全库 Episode
--       时顺手按季统计库内集数存入本表，MP 订阅同步直接本地算（已播 - 库内），不再实时打 Emby。
--       本表为 Emby 侧按季库内集数，与 tmdb_season（TMDB 侧按季已播集数）对称。
--       新库由 create_all 自动建立，此 SQL 供存量库手工执行。
-- 执行: psql -h 192.168.31.10 -U unisub -d unisub -f backend/migrations/005_emby_season_cache.sql
-- 对应模型: app/models/emby_season_cache.py

CREATE TABLE IF NOT EXISTS emby_season_cache (
    tmdb_id INTEGER NOT NULL,
    season INTEGER NOT NULL,                 -- 季号（不含特典季 0）
    episode_count INTEGER DEFAULT 0,         -- Emby 库中该季实际剧集文件数
    updated_at TIMESTAMPTZ,
    PRIMARY KEY (tmdb_id, season)
);
