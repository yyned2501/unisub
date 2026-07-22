# NextFind API 参考文档 (v3 — 2026-07-22 全量实测版)

> 本文档记录 NextFind 所有 OpenAPI 端点的**实测返回值**，包含完整字段列表和参数类型。
> 供 Claude Code 在集成时直接参考，避免参数类型错误。

---

## 目录

1. [基础信息](#1-基础信息)
2. [查询类](#2-查询类)
3. [预览与额度](#3-预览与额度)
4. [转存与目录](#4-转存与目录)
5. [删除](#5-删除)
6. [历史](#6-历史)
7. [订阅与追更](#7-订阅与追更)
8. [设置](#8-设置)
9. [本地库状态](#9-本地库状态)
10. [参数类型速查](#10-参数类型速查)
11. [Web API](#11-web-api)

---

## 1. 基础信息

```
Base:    http://192.168.31.10:8092/api/openapi
Header:  X-API-Key: zv8icxxmmje0cd1pwknjr26ho9dd4y7u
Content: application/json (for POST/PUT/DELETE，必须带 Content-Type: application/json)
```

**⚠️ 关键约定：Body 中 `tmdb_id` 必须是字符串 `"1396"`，不是整数 `1396`。**
部分端点（如 `transfer`）传 int 也能工作，但统一用 `str(tmdb_id)` 最安全。

---

## 2. 查询类

### 2.1 `GET /search` — 全局 TMDB 搜索

**Query 参数：**

| 参数 | 类型 | 必填 | 说明 |
|:---|:---|:---:|:---|
| `query` | string | 是 | 搜索关键词 |
| `type` | string | 否 | `全部` / `电影` / `剧集`（中文值，不是 `movie`/`tv`） |

**返回值：**
```json
{
  "status": "success",
  "data": [
    {
      "id": "1396",
      "title": "绝命毒师",
      "type": "电视剧",
      "raw_type": "tv",
      "poster": "/api/tmdb/image/rqliuvX7NdknSHu5qaSDfESplQi.jpg",
      "rating": "8.9",
      "year": "2008",
      "status": "none",
      "shield_badge": false,
      "has_ignored_season": false,
      "fillable_movie_tag": "",
      "is_in_library": false,
      "genre_ids": [18, 80],
      "origin_country": ["US"],
      "original_language": "en",
      "_popularity": 116.5476,
      "_release_date": "2008-01-20",
      "_vote_average": 8.942
    }
  ]
}
```

**字段说明：**
- `id` — TMDB ID（字符串），不是 `tmdb_id`
- `raw_type` — 英文类型标识（`tv` / `movie`）
- `type` — 中文显示名（`电视剧` / `电影`）
- `shield_badge` — 是否有神盾资源
- `is_in_library` — 是否在本地库中
- `_popularity`, `_release_date`, `_vote_average` — 以下划线开头，TMDB 原始数据

### 2.2 `GET /shield/search` — 神盾模式查询

**Query 参数：**

| 参数 | 类型 | 必填 | 说明 |
|:---|:---|:---:|:---|
| `sha1` | string | 二选一 | 文件 SHA1 哈希 |
| `mediasource_id` | string | 二选一 | 媒体源 ID |
| `tmdb_id` | string | 否 | 可选，辅助匹配 |

**返回值（命中）：** 待补充（暂无有效 sha1/mediasource_id 实测）

**返回值（未命中）：**
```json
{
  "status": "error",
  "message": "未命中神盾缓存，且无对应灰标资源"
}
```

**返回值（缺参数）：**
```json
{
  "status": "error",
  "message": "sha1 和 mediasource_id 不能同时为空"
}
```

### 2.3 `GET /resources/search` — 搜索网盘与种子资源

**Query 参数：**

| 参数 | 类型 | 必填 | 说明 |
|:---|:---|:---:|:---|
| `tmdb_id` | string | 是 | TMDB ID |
| `media_type` | string | 是 | `tv` 或 `movie` |
| `season` | int | 否 | 季号（tv 时建议传） |
| `episode` | int | 否 | 集号（tv 时建议传） |

**返回值：**
```json
{
  "status": "success",
  "count": 15,
  "data": [
    {
      "slug": "hdhive://ef94e1b6003d438fb4445ee1be53e1e5",
      "title": "绝命毒师",
      "pan_type": "radar",
      "media_url": "https://hdhive.com/tv/0f70263debd811ed8d4e0242ac190003",
      "media_slug": "0f70263debd811ed8d4e0242ac190003",
      "share_size": "413G",
      "video_resolution": ["4K"],
      "source": ["BDRip/BluRayEncode"],
      "subtitle_language": ["简英双语"],
      "subtitle_type": ["内封"],
      "remark": "2160P H265 自压 轻量计划",
      "unlock_points": 10,
      "unlocked_users_count": 8,
      "validate_status": null,
      "validate_message": null,
      "last_validated_at": null,
      "is_official": false,
      "is_unlocked": false,
      "user": { "nickname": "HDHiveAPI" },
      "created_at": "2026-07-16 19:58:09",
      "updated_at": "2026-07-16 19:58:09",
      "custom_keywords": [],
      "_is_from_list_cache": false,
      "year": "2008",
      "name": "绝命毒师",
      "movie_attributes": {
        "resolution": "4K",
        "remux": "",
        "color": "",
        "audio": "",
        "group": "",
        "ext": ""
      },
      "parsed_episodes": "S01E01-E07 S02E01-E13 S03E01-E13 S04E01-E13 S05E01-E16",
      "channel_name": "HDHiveAPI",
      "source_type": "hdhive",
      "db_tmdb_id": "1396",
      "tmdb_id": "1396",
      "db_media_type": "tv",
      "media_type": "tv",
      "real_sharer": "Ash-Media",
      "db_raw_text": "名称：绝命毒师 (2008)\n备注：2160P H265 自压 轻量计划\n标签：4K BDRip/BluRayEncode 简英双语",
      "matched_words": ["2160P", "绝命毒师", "2008", "H265"]
    }
  ]
}
```

---

## 3. 预览与额度

### 3.1 `GET /quota` — 查询额度与积分

**返回值：**
```json
{
  "status": "success",
  "data": {
    "hdhive": "AWdress SVIP 1347次/3381积分",
    "ayclub": "未开启"
  }
}
```

### 3.2 `POST /preview` — 触发探针解包

**Body 参数：**

| 参数 | 类型 | 必填 | 说明 |
|:---|:---|:---:|:---|
| `slug` | string | 是 | 资源标识，如 `nextfind://...` 或 `hdhive://...` |

**返回值（无效 slug）：**
```json
{
  "status": "error",
  "message": "无效的 NextFind 链接"
}
```

**返回值（成功）：** 待有效 slug 实测，预期返回文件树 + sha1 等探针信息。

### 3.3 `POST /hdhive/unlock` — HDHive 积分解锁

**Body 参数：**

| 参数 | 类型 | 必填 | 说明 |
|:---|:---|:---:|:---|
| `id` | string | 是 | 资源 ID |
| `type` | string | 是 | 资源类型 |

**状态：** ⚠️ **当前返回 500 Internal Server Error**（NextFind 后端 bug）

---

## 4. 转存与目录

### 4.1 `POST /transfer` — 一键转存到网盘

**Body 参数：**

| 参数 | 类型 | 必填 | 说明 |
|:---|:---|:---:|:---|
| `slug` | string | 二选一 | 资源标识（hdhive:// 或 nextfind://） |
| `tmdb_id` | int | 二选一 | TMDB ID（按 TMDB 转存） |
| `target_folder` | string | 是 | 目标文件夹路径 |

**返回值：**
```json
{
  "status": "success",
  "message": "转存任务已提交后台执行"
}
```
HTTP 200。任务异步执行，不阻塞。

### 4.2 `GET /directories` — 查询网盘目录

**Query 参数：**

| 参数 | 类型 | 必填 | 说明 |
|:---|:---|:---:|:---|
| `cid` | string | 否 | 父目录 ID，不传返回根目录 |

**返回值（根目录，12 条）：**
```json
{
  "status": "success",
  "data": [
    {
      "cid": "3321397512894416877",
      "name": "最近接收",
      "parent_cid": "0"
    }
  ]
}
```

### 4.3 `POST /directories` — 创建网盘目录

**Body 参数：**

| 参数 | 类型 | 必填 | 说明 |
|:---|:---|:---:|:---|
| `parent_cid` | string | 是 | 父目录 ID |
| `name` | string | 是 | 新目录名称 |

**返回值：**
```json
{
  "status": "success",
  "message": "创建成功",
  "cid": "3478636798983275927",
  "name": "测试目录"
}
```

---

## 5. 删除

### 5.1 `DELETE /media/episode` — 静默删除指定集

**Query 参数：**

| 参数 | 类型 | 必填 | 说明 |
|:---|:---|:---:|:---|
| `tmdb_id` | string | 是 | TMDB ID |
| `season` | int | 是 | 季号 |
| `episode` | int | 是 | 集号 |

**返回值（未找到）：**
```json
{
  "status": "error",
  "message": "未在本地库找到对应的集"
}
```

### 5.2 `DELETE /media/season` — 静默删除整季

**Query 参数：**

| 参数 | 类型 | 必填 | 说明 |
|:---|:---|:---:|:---|
| `tmdb_id` | string | 是 | TMDB ID |
| `season` | int | 是 | 季号 |

**返回值（未找到）：**
```json
{
  "status": "error",
  "message": "未在本地库找到对应的季"
}
```

### 5.3 `DELETE /media/movie` — 静默删除电影

**Query 参数：**

| 参数 | 类型 | 必填 | 说明 |
|:---|:---|:---:|:---|
| `tmdb_id` | string | 是 | TMDB ID |

**返回值（未找到）：**
```json
{
  "status": "error",
  "message": "未在本地库找到该电影"
}
```

---

## 6. 历史

### 6.1 `GET /history` — 获取转存历史

**Query 参数：**

| 参数 | 类型 | 必填 | 说明 |
|:---|:---|:---:|:---|
| `page` | int | 否 | 页码，默认 1 |
| `page_size` | int | 否 | 每页条数，默认 20 |

**返回值：**
```json
{
  "status": "success",
  "data": [
    {
      "id": 5850,
      "tmdb_id": "296915",
      "media_type": "tv",
      "season": null,
      "episode": null,
      "transferred_resolution": "39210100738.0",
      "slug": "https://115.com/s/swsos0x3wye?password=32ff",
      "transfer_time": "2026-07-22 14:26:27",
      "is_slug_transferred": 1,
      "remark": "[剧集] 依然的喜事 (2026) | S01E01-E08 ...",
      "source": "115网盘资源收藏",
      "folder_path": "待整理/转存",
      "trigger_reason": "追更+洗版",
      "media_tags": "4K,HDR,EAC3,MP4",
      "episode_str": "S01E01-E08",
      "title": "依然的喜事",
      "poster": null,
      "year": null,
      "movie_attributes_json": "{...}"
    }
  ]
}
```

### 6.2 `DELETE /history/all` — 清空全部转存历史

**返回值：**
```json
{
  "status": "success",
  "message": "成功清空 847 条记录"
}
```

### 6.3 `DELETE /history/item` — 删除指定历史

**Query 参数：**

| 参数 | 类型 | 必填 | 说明 |
|:---|:---|:---:|:---|
| `tmdb_id` | string | 二选一 | 按 TMDB ID 删除 |
| `title` | string | 二选一 | 按标题精准匹配删除 |

**返回值：**
```json
{
  "status": "success",
  "message": "成功删除历史记录"
}
```
注意：即使没有匹配的记录，也返回 success。

---

## 7. 订阅与追更

### 7.1 `GET /subscriptions` — 获取活跃订阅列表

**返回值（数组，非 `{status, data}` 包装）：**
```json
[
  {
    "tmdb_id": "89861",
    "title": "密室大逃脱",
    "media_type": "tv",
    "poster_path": "/api/tmdb/image/qQ221G1KxusTIotpTi4cxDk6O13.jpg",
    "poster": "/api/tmdb/image/qQ221G1KxusTIotpTi4cxDk6O13.jpg",
    "target_resolution": "best",
    "status": "subscribing",
    "sub_status": "active",
    "current_score": 0,
    "created_at": "2026-07-22 08:09:11",
    "source": "openapi",
    "fail_count": 0,
    "username": "",
    "finish_time": null,
    "year": "2019",
    "rating": 7.6,
    "total_episodes": 97,
    "local_episodes": 93,
    "expiry_date": 0,
    "is_in_library": false
  }
]
```

**完整字段列表：**
`tmdb_id`, `title`, `media_type`, `poster_path`, `poster`, `target_resolution`, `status`, `sub_status`, `current_score`, `created_at`, `source`, `fail_count`, `username`, `finish_time`, `year`, `rating`, `total_episodes`, `local_episodes`, `expiry_date`, `is_in_library`

**状态字段说明：**
- `status` — 内部状态（`subscribing`, `cancelled` 等）
- `sub_status` — 用户可见状态（`active`, `cancelled`, `completed`）
- **判断是否取消**：用 `sub_status` 或 `status`，取最先存在的
- `is_in_library` — 是否已入库
- `total_episodes` — ⚠️ TMDB 规划全集数，**不是已播出数**。电影恒为 0

### 7.2 `POST /subscriptions/add` — 添加订阅

**Body 参数：**

| 参数 | 类型 | 必填 | 说明 |
|:---|:---|:---:|:---|
| `tmdb_id` | **string** | 是 | TMDB ID（**必须字符串**） |
| `media_type` | string | 是 | `tv` 或 `movie` |
| `title` | string | 否 | 可选，辅助标题 |

**返回值：**
```json
{
  "status": "success",
  "message": "订阅成功，已加入第一队列排队进行全量搜索..."
}
```
或已存在时返回 `"already exists"` 相关消息。

### 7.3 `POST /subscriptions/remove` — 取消订阅

**Body 参数：**

| 参数 | 类型 | 必填 | 说明 |
|:---|:---|:---:|:---|
| `tmdb_id` | **string** | 是 | TMDB ID（**必须字符串**） |
| `media_type` | string | 是 | `tv` 或 `movie` |

**返回值：**
```json
{
  "status": "success",
  "message": "已取消订阅"
}
```
注意：对已取消的条目再次调用，仍然返回 success。

### 7.4 `POST /subscriptions/info` — 批量查询入库进度

**Body 参数：**

| 参数 | 类型 | 必填 | 说明 |
|:---|:---|:---:|:---|
| `items` | array | 是 | 查询项列表 |
| `items[].tmdb_id` | **string** | 是 | TMDB ID（**必须字符串**） |
| `items[].media_type` | string | 是 | `tv` 或 `movie` |

**返回值：**
```json
{
  "status": "success",
  "data": [
    {
      "tmdb_id": "1396",
      "media_type": "tv",
      "title": "绝命毒师",
      "poster": "/api/tmdb/image/rqliuvX7NdknSHu5qaSDfESplQi.jpg",
      "poster_path": "/api/tmdb/image/rqliuvX7NdknSHu5qaSDfESplQi.jpg",
      "year": "2008",
      "rating": 8.948,
      "local_episodes": 62,
      "total_episodes": 62,
      "expiry_date": 0,
      "is_in_library": true
    }
  ]
}
```

**⚠️ 关键：**
- `total_episodes` 是 TMDB 全集数，**不是已播出数**。在播剧要用 `tmdb_aired_eps`（从 TMDB 获取）计算真实缺集。
- 电影 `total_episodes` 恒为 0，`local_episodes` 为 0 或 1。
- 电影完成判断：`is_in_library == true` 或 `local_episodes > 0`

### 7.5 `POST /media/fill_missing` — 触发补缺集搜索

**Body 参数：**

| 参数 | 类型 | 必填 | 说明 |
|:---|:---|:---:|:---|
| `tmdb_id` | **string** | 是 | TMDB ID（**必须字符串**） |
| `media_type` | string | 是 | `tv` 或 `movie` |
| `title` | string | 否 | 可选，辅助标题 |

**返回值：**
```json
{
  "status": "success",
  "message": "补缺任务已提交队列"
}
```
HTTP 200。任务推入高优队列，NextFind 调度器在下一轮循环中搜索并下载。

### 7.6 `POST /ignored_episodes/toggle` — 切换忽略季状态

**Body 参数：**

| 参数 | 类型 | 必填 | 说明 |
|:---|:---|:---:|:---|
| `tmdb_id` | int | 是 | TMDB ID |
| `season` | int | 是 | 季号 |

**状态：** ⚠️ **当前返回 500 Internal Server Error**（NextFind 后端 bug）

---

## 8. 设置

### 8.1 `GET /logs` — 获取系统日志

**Query 参数：**

| 参数 | 类型 | 必填 | 说明 |
|:---|:---|:---:|:---|
| `lines` | int | 否 | 行数，默认 50 |

**返回值：**
```json
{
  "status": "success",
  "data": [
    "  File \"/usr/local/lib/python3.12/site-packages/fastapi/routing.py\", line 344...\n",
    "    return await dependant.call(**values)\n",
    "  ...\n"
  ]
}
```
`data` 是字符串数组，每行一条日志（含换行符）。

### 8.2 `GET /settings/tg_channels` — 获取 TG 频道列表

**返回值：**
```json
{
  "status": "success",
  "data": [
    {
      "name": "115网盘资源收藏",
      "id": "-1002167886055",
      "level": 48,
      "logo": "/api/tg/image/-1002167886055.jpg?t=1780148272",
      "stats": {
        "captured": 98,
        "transferred": 22
      }
    }
  ]
}
```

### 8.3 `POST /settings/tg_channels` — 修改 TG 频道

**Body 参数：**

| 参数 | 类型 | 必填 | 说明 |
|:---|:---|:---:|:---|
| `channels` | array | 是 | 频道 ID 列表，如 `["@aliyun_share"]` |

**返回值：** 待实测（非破坏性操作未测）

### 8.4 `GET /settings/rss` — 获取 RSS 订阅源列表

**返回值：**
```json
{
  "status": "success",
  "data": []
}
```
当前为空数组。

### 8.5 `POST /settings/rss` — 修改 RSS 订阅源

**Body 参数：**

| 参数 | 类型 | 必填 | 说明 |
|:---|:---|:---:|:---|
| `sources` | array | 是 | RSS URL 列表 |

**返回值：** 待实测（非破坏性操作未测）

### 8.6 `POST /settings/rules` — 修改资源过滤规则

**Body 参数：**

| 参数 | 类型 | 必填 | 说明 |
|:---|:---|:---:|:---|
| `blacklist` | array | 否 | 黑名单关键词，如 `["韩语", "印度"]` |
| `whitelist` | array | 否 | 白名单关键词，如 `["4K"]` |

**返回值：**
```json
{
  "status": "success",
  "message": "过滤规则已更新"
}
```
**注意：没有 GET 方法**（`GET /settings/rules` 返回 405 Method Not Allowed）。

### 8.7 `POST /settings/transfer_folder` — 修改默认转存目录

**Body 参数：**

| 参数 | 类型 | 必填 | 说明 |
|:---|:---|:---:|:---|
| `folder_id` | string | 是 | 目标目录 ID |
| `folder_name` | string | 是 | 目标目录名称 |

**返回值：**
```json
{
  "status": "success",
  "message": "转存目录已更新"
}
```
**注意：没有 GET 方法**（`GET /settings/transfer_folder` 返回 405 Method Not Allowed）。

---

## 9. 本地库状态

### 9.1 `GET /local_library/filter` — 过滤本地库状态

**Query 参数：**

| 参数 | 类型 | 必填 | 说明 |
|:---|:---|:---:|:---|
| `status_filter` | string | 是 | `missing` / `error` / `duplicate` |

**状态：** ❌ **当前 500 Internal Server Error**（NextFind 后端 `ImportError: cannot import name get_local_library`）
- `missing` 和 `error` 返回空响应
- `duplicate` 返回 `Internal Server Error`

---

## 10. 参数类型速查

**⚠️ 核心规则：`tmdb_id` 在 Body 中必须是字符串，在 Query 参数中可以传 int。**

| 端点 | 方法 | `tmdb_id` 类型 | 备注 |
|:---|:---:|:---:|:---|
| `/search` | GET | Query `string` | `type` 用中文值 |
| `/shield/search` | GET | Query `string` | 可选 |
| `/resources/search` | GET | Query `string` | 必填 |
| `/quota` | GET | — | 无参数 |
| `/preview` | POST | — | 用 `slug` |
| `/hdhive/unlock` | POST | — | ⚠️ 500 |
| `/transfer` | POST | Body `int` | 实测 int 可以 |
| `/directories` | GET/POST | — | 用 `cid` |
| `/media/episode` | DELETE | Query `string` | |
| `/media/season` | DELETE | Query `string` | |
| `/media/movie` | DELETE | Query `string` | |
| `/history` | GET | — | |
| `/history/all` | DELETE | — | |
| `/history/item` | DELETE | Query `string` | 或 `title` |
| `/subscriptions` | GET | — | |
| `/subscriptions/add` | POST | **Body `string`** | |
| `/subscriptions/remove` | POST | **Body `string`** | |
| `/subscriptions/info` | POST | **items[].tmdb_id `string`** | |
| `/media/fill_missing` | POST | **Body `string`** | |
| `/ignored_episodes/toggle` | POST | Body `int` | ⚠️ 500 |
| `/logs` | GET | — | `lines` int |
| `/settings/tg_channels` | GET/POST | — | |
| `/settings/rss` | GET/POST | — | |
| `/settings/rules` | POST | — | 无 GET |
| `/settings/transfer_folder` | POST | — | 无 GET |
| `/local_library/filter` | GET | — | ❌ 500 |

---

## 11. Web API（Cookie 鉴权）

### 11.1 登录

```bash
curl -X POST -d "username=yangyang&password=yy920120" \
  "https://nf.js.248226785.xyz:8443/login" \
  -c /tmp/nf_cookies.txt
```

Cookie: `nextmedia_session`（30 天有效期）

### 11.2 `GET /api/local_library` — 本地库逐集详情

**Query 参数：**

| 参数 | 类型 | 必填 | 说明 |
|:---|:---|:---:|:---|
| `type` | string | 是 | `tv` 或 `movie` |
| `tmdb_id` | int | 是 | TMDB ID |

**返回值：**
```json
{
  "status": "success",
  "data": {
    "type": "tv",
    "matrix": [
      {
        "season": 0,
        "episodes": [
          {
            "ep": 1,
            "has_local": true,
            "is_aired": true,
            "is_extra": false,
            "versions": [
              {
                "filename": "/media/Symedia/MoviePilot/电视剧/...strm",
                "ep_emby_id": "1265537",
                "mediasourceid": "1265537",
                "tags": ["1080P", "AAC stereo", "MP4", "0.27G"],
                "folder_index": 0
              }
            ]
          }
        ]
      }
    ]
  }
}
```

**缺集计算：** `is_aired == true AND has_local == false` → 真缺集

### 11.3 `GET /api/discover` — 全局缺集列表

Query: `status=缺失集`
返回值：待实测。

---

## 变更记录

- **v3 (2026-07-22)**：全量实测所有端点，补充完整返回值结构、字段列表、参数类型。新增 `/shield/search`, `/settings/rules`, `/settings/transfer_folder`。标记 `/hdhive/unlock` 和 `/ignored_episodes/toggle` 为 500 故障。
- **v2 (2026-07-16)**：初版，含 OpenAPI 和 Web API 两条路径。