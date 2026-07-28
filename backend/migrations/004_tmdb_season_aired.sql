-- UniSub 迁移 004: tmdb_season 新增 aired_count（该季已播出集数）
-- 背景: TMDB 存在脏数据——announced 但未开播的季带着 episode_count（计划总集数），
--       MP 会据此给"根本不存在的集"建订阅、反复搜索。新增 aired_count 记录每季
--       实际已播集数（0=未开播），MP 订阅的季集结构（get_seasons_map）只纳入
--       aired_count>0 的季，且集数范围以已播集数为准，从源头过滤未播季/未播集。
--       aired_count 由 TMDBService._save_seasons 在刷新 /tv 详情时计算写入。
-- 执行: psql -h 192.168.31.10 -U unisub -d unisub -f backend/migrations/004_tmdb_season_aired.sql
-- 对应模型: app/models/tmdb_season.py

ALTER TABLE tmdb_season ADD COLUMN IF NOT EXISTS aired_count INTEGER DEFAULT 0;
