/**
 * 自动订阅 — 默认配置与元数据常量。
 * 从 AutoSubscribeSettings.vue 抽离，避免内联在组件中。
 */
import type { AutoSubConfig, SelectOption } from '@/types'

/** 自动订阅默认配置 */
export const DEFAULT_CONFIG: AutoSubConfig = {
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

/** 自动订阅默认元数据（下拉选项） */
export const DEFAULT_META: {
  douban_ranks: SelectOption[]
  maoyan_platforms: SelectOption[]
  maoyan_media_types: SelectOption[]
  seasons: SelectOption[]
} = {
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
    { value: '全网', label: '全网' },
    { value: '腾讯视频', label: '腾讯视频' },
    { value: '爱奇艺', label: '爱奇艺' },
    { value: '优酷', label: '优酷' },
    { value: '芒果TV', label: '芒果TV' },
    { value: '搜狐视频', label: '搜狐视频' },
    { value: '乐视', label: '乐视' },
    { value: 'PPTV', label: 'PPTV' },
  ],
  maoyan_media_types: [
    { value: 'series', label: '电视剧+网络剧' },
    { value: 'tv', label: '电视剧' },
    { value: 'web', label: '网络剧' },
    { value: 'variety', label: '综艺' },
  ],
  seasons: [
    { value: '当前', label: '当前季' },
    { value: '春', label: '春季' },
    { value: '夏', label: '夏季' },
    { value: '秋', label: '秋季' },
    { value: '冬', label: '冬季' },
  ],
}
