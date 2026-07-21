/**
 * 自动订阅 — 默认配置与元数据常量。
 * 从 AutoSubscribeSettings.vue 抽离，避免内联在组件中。
 */

export const DEFAULT_CONFIG = {
  enabled: false,
  min_year: 0,
  min_vote: 0,
  media_type: 'all',
  schedule_cron: '0 8 * * *',
  douban_enabled: false,
  douban_ranks: ['movie-hot-gaia', 'tv-hot'],
  douban_rsshub: 'https://rsshub.app',
  douban_rss_custom: '',
  mikan_enabled: false,
  mikan_season: '当前',
  mikan_year: 0,
  mikan_resolve_detail: true,
  maoyan_enabled: false,
  maoyan_movie_box: true,
  maoyan_web_platforms: [],
  maoyan_web_types: [],
  maoyan_num: 10,
  proxy_url: '',
}

export const DEFAULT_META = {
  douban_ranks: [
    { value: 'movie-ustop', label: '北美票房榜' },
    { value: 'movie-weekly', label: '一周口碑榜' },
    { value: 'movie-top250', label: 'Top250' },
    { value: 'movie-hot-gaia', label: '热门电影' },
    { value: 'tv-hot', label: '热门剧集' },
    { value: 'tv-variety-show', label: '综艺' },
    { value: 'movie-real-time', label: '实时热门电影' },
  ],
  maoyan_platforms: [
    { value: '腾讯视频', label: '腾讯视频' },
    { value: '爱奇艺', label: '爱奇艺' },
    { value: '优酷', label: '优酷' },
    { value: '芒果TV', label: '芒果TV' },
    { value: '哔哩哔哩', label: '哔哩哔哩' },
    { value: '抖音', label: '抖音' },
    { value: '快手', label: '快手' },
    { value: '西瓜视频', label: '西瓜视频' },
  ],
  maoyan_media_types: [
    { value: 'tv', label: '电视剧' },
    { value: 'movie', label: '电影' },
    { value: '动漫', label: '动漫' },
  ],
  seasons: [
    { value: '当前', label: '当前季' },
    { value: '春', label: '春季' },
    { value: '夏', label: '夏季' },
    { value: '秋', label: '秋季' },
    { value: '冬', label: '冬季' },
  ],
}