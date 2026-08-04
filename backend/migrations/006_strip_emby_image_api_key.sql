-- UniSub 迁移 006: 清除 emby_cache.emby_image_url 中泄露的 Emby api_key
-- 背景: 历史版本把图片直链写成 {emby_base}/Items/{id}/Images/Primary?api_key={key}，
--       api_key 随响应进入浏览器（<img src>），存在泄露风险。
--       代码已改为：列里只存无签名代理路径 /api/emby/image/{id}（仅作为"有海报"标记），
--       响应时由 core/image_sign.py 动态签发短期 URL，后端代理端点用 X-Emby-Token 头取图。
-- 执行: psql -h 192.168.31.10 -U unisub -d unisub -f backend/migrations/006_strip_emby_image_api_key.sql

UPDATE emby_cache
SET emby_image_url = '/api/emby/image/' || emby_series_id
WHERE emby_series_id IS NOT NULL;

UPDATE emby_cache
SET emby_image_url = NULL
WHERE emby_series_id IS NULL;
