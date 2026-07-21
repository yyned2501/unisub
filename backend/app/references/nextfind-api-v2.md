# NextFind API 参考文档 (v2 — 2026-07-16 实测版)

> 本文档记录 NextFind 所有可用 API 的实测结果，包括 OpenAPI 和 Web API 两条路径。
> 供 Claude Code 在集成时直接参考。

---

## 目录

1. [架构概览](#1-架构概览)
2. [OpenAPI（X-API-Key 鉴权）](#2-openapix-api-key-鉴权)
3. [Web API（Cookie 鉴权）](#3-web-apicookie-鉴权)
4. [缺集数据对比](#4-缺集数据对比)
5. [集成建议](#5-集成建议)

---

## 1. 架构概览

NextFind 暴露两套 API：

| 维度 | OpenAPI | Web API |
|:---|:---|:---|
| 地址 | `http://192.168.31.10:8092/api/openapi` | `https://nf.js.248226785.xyz:8443/api` |
| 鉴权 | Header `X-API-Key: zv8icxxmmje0cd1pwknjr26ho9dd4y7u` | Cookie `nextmedia_session` |
| 登录方式 | 无需登录 | `POST /login` with `username=yangyang&password=yy920120` |
| 适用场景 | 简单操作（搜索/订阅/转存） | 复杂查询（本地库逐集详情） |

---

## 2. OpenAPI（X-API-Key 鉴权）

### 2.1 基础信息

```
Base:    http://192.168.31.10:8092/api/openapi
Header:  X-API-Key: zv8icxxmmje0cd1pwknjr26ho9dd4y7u
Content: application/json (for POST)
```

### 2.2 全部端点实测结果

#### ✅ 查询类

| 端点 | 方法 | 参数 | 状态 | 说明 |
|:---|:---:|:---|:---:|:---|
| `/search` | GET | `query`, `type`(全部/电影/剧集) | ✅ 200 | TMDB 搜索 |
| `/resources/search` | GET | `tmdb_id`, `media_type`, `season`, `episode` | ✅ 200 | 搜索网盘与种子资源，含神盾标志/洗版权重 |

#### ✅ 预览与额度

| 端点 | 方法 | 参数 | 状态 | 说明 |
|:---|:---:|:---|:---:|:---|
| `/quota` | GET | 无 | ✅ 200 | 当前积分与 API 次数 |
| `/preview` | POST | `slug`(资源标识) | ✅ 200 | 探针解包，返回文件树+sha1 |

#### ✅ 转存与目录

| 端点 | 方法 | 参数 | 状态 | 说明 |
|:---|:---:|:---|:---:|:---|
| `/transfer` | POST | `tmdb_id`, `target_folder` | ✅ 可用 | 一键转存到网盘 |
| `/directories` | GET | `cid`(可选) | ✅ 200 | 查询网盘目录，不传 cid 返回根目录 (12个) |
| `/directories` | POST | `parent_cid`, `name` | ✅ 可用 | 创建网盘目录 |

#### ✅ 删除

| 端点 | 方法 | 参数 | 状态 | 说明 |
|:---|:---:|:---|:---:|:---|
| `/media/episode` | DELETE | `tmdb_id`, `season`, `episode` | ✅ 可用 | 静默删除指定集 |
| `/media/season` | DELETE | `tmdb_id`, `season` | ✅ 可用 | 静默删除整季 |
| `/media/movie` | DELETE | `tmdb_id` | ✅ 可用 | 静默删除电影 |

#### ✅ 历史

| 端点 | 方法 | 参数 | 状态 | 说明 |
|:---|:---:|:---|:---:|:---|
| `/history` | GET | 无 | ✅ 200 | 转存历史 |
| `/history/all` | DELETE | 无 | ✅ 可用 | 清空全部转存历史 |
| `/history/item` | DELETE | `tmdb_id` 或 `title` | ✅ 可用 | 删除指定历史 |

#### ✅ 订阅与追更

| 端点 | 方法 | 参数 | 状态 | 说明 |
|:---|:---:|:---|:---:|:---|
| `/subscriptions` | GET | 无 | ✅ 200 | 活跃订阅列表 |
| `/subscriptions/add` | POST | `tmdb_id` (int), `media_type` | ✅ 可用 | 添加订阅 |
| `/subscriptions/remove` | POST | `tmdb_id` (int), `media_type` | ✅ 可用 | 取消订阅 |
| `/subscriptions/info` | POST | `items: [{"tmdb_id": "str", "media_type": "tv"}]` | ✅ 200 | **批量查询入库进度**，返回 `local_episodes`, `total_episodes` |
| `/media/fill_missing` | POST | `tmdb_id`: **string**!, `media_type` | ✅ 200 | **触发补缺集搜索**，推入高优队列 |
| `/ignored_episodes/toggle` | POST | `tmdb_id`, `season` | ✅ 可用 | 切换忽略季状态 |

#### ✅ 设置

| 端点 | 方法 | 参数 | 状态 | 说明 |
|:---|:---:|:---|:---:|:---|
| `/logs` | GET | 无 | ✅ 200 | 系统日志（含完整 traceback） |
| `/settings/tg_channels` | GET | 无 | ✅ 200 | TG 频道列表（9 个频道含统计） |
| `/settings/tg_channels` | POST | - | ✅ 可用 | 修改 TG 频道 |
| `/settings/rss` | GET | 无 | ✅ 200 | RSS 订阅源列表 |
| `/settings/rss` | POST | - | ✅ 可用 | 修改 RSS 订阅源 |
| `/settings/rules` | POST | - | ✅ 可用 | 修改资源过滤规则 |
| `/settings/transfer_folder` | POST | - | ✅ 可用 | 修改默认转存目录 |
| `/hdhive/unlock` | POST | `id`, `type` | ✅ 可用 | HDHive 积分解锁 |

#### ❌ 不可用

| 端点 | 方法 | 参数 | 状态 | 说明 |
|:---|:---:|:---|:---:|:---|
| `/local_library/filter` | GET | `status_filter`(missing/error/duplicate) | ❌ **500** | **NextFind后端bug** — `ImportError: cannot import name get_local_library` |

### 2.3 ⚠️ 参数坑

**`tmdb_id` 必须是字符串！**
```python
# ❌ 会报 422
{"tmdb_id": 280049, "media_type": "tv"}

# ✅ 正确
{"tmdb_id": "280049", "media_type": "tv"}
```
影响端点：`/subscriptions/info`, `/media/fill_missing`

### 2.4 `POST /media/fill_missing` 返回值

```json
{
  "status": "success",
  "message": "补缺任务已提交队列"
}
```
HTTP 200。任务提交后 NextFind 调度器会在下一轮循环中搜索并下载。

### 2.5 `POST /subscriptions/info` 返回值

```json
{
  "status": "success",
  "data": [{
    "tmdb_id": "280049",
    "media_type": "tv",
    "title": "地狱模式 ...",
    "local_episodes": 12,      // 本地已有集数
    "total_episodes": 24,      // ⚠️ TMDB规划全集数，非已播出数
    "is_in_library": false,    // 是否完整入库
    "expiry_date": 0,
    "year": "2026",
    "rating": 7.4,
    "poster": "/api/tmdb/image/..."
  }]
}
```

**⚠️ 关键：`total_episodes` 是 TMDB 全集数（如 24 集），不是已播出数。** 对于在播番，要用 `tmdb_aired_eps`（从 TMDB 获取）来计算真实缺集。

---

## 3. Web API（Cookie 鉴权）

### 3.1 登录流程

```bash
# Step 1: 登录获取 cookie
curl -X POST -d "username=yangyang&password=yy920120" \
  "https://nf.js.248226785.xyz:8443/login" \
  -c /tmp/nf_cookies.txt

# Step 2: 后续请求带 cookie
curl -b /tmp/nf_cookies.txt \
  "https://nf.js.248226785.xyz:8443/api/local_library?type=tv&tmdb_id=219934"
```

Cookie: `nextmedia_session=ImFkbWluIg.aljaRg.fnAS9wpiBbXjrZYXXbxjOfEoIFQ`（30天有效期）

### 3.2 实测可用端点

| 端点 | 方法 | 参数 | 状态 | 说明 |
|:---|:---:|:---|:---:|:---|
| `/api/local_library` | GET | `type`(tv/movie), `tmdb_id` | ✅ **200** | **本地库逐集详情 ← 核心发现** |
| `/api/discover` | GET | `status=缺失集` | ✅ 可用 | 全局缺集列表（走 Web API） |

### 3.3 ⭐ `GET /api/local_library` 返回值结构

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
            "has_local": true,       // ✅ 本地是否存在
            "is_aired": true,        // ✅ 是否已播出
            "is_extra": false,       // ✅ 是否花絮/特典
            "versions": [
              {
                "filename": "/media/Symedia/MoviePilot/电视剧/...strm",
                "ep_emby_id": "1265537",     // Emby 媒体 ID
                "mediasourceid": "1265537",  // 媒体源 ID
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

### 3.4 缺集计算逻辑

**真正缺集** = `is_aired == true AND has_local == false`

这解决了 OpenAPI 方案的核心痛点：区分"未播出"和"真缺集"。

#### 实测数据：种地吧 tmdb_id=219934

| 季 | 总集 | 已有 | 已播 | **真缺** | 花絮 |
|:---|:---:|:---:|:---:|:---:|:---:|
| Season 0 | 85 | 85 | 85 | **0** | 0 |
| Season 1 | 91 | 91 | 91 | **0** | 0 |
| Season 2 | 63 | 63 | 63 | **0** | 20 |
| Season 3 | 80 | 80 | 80 | **0** | 0 |
| **Season 4** | **36** | **34** | **36** | **2** (ep 35,36) | 0 |

---

## 4. 缺集数据对比

### 三种方案对比

| 维度 | OpenAPI `subscriptions/info` | OpenAPI `local_library/filter` | **Web API `local_library`** |
|:---|:---:|:---:|:---:|
| 鉴权方式 | API Key | API Key | Cookie |
| 每集颗粒度 | ❌ 只有总数 | ❌ 未知(500) | ✅ **逐集详情** |
| `is_aired` 标志 | ❌ 无 | ❌ 未知 | ✅ **有** |
| 区分未播vs真缺 | ❌ 不能 | ❌ 未知 | ✅ **可以** |
| 文件详情/emby_id | ❌ 无 | ❌ 未知 | ✅ **含 tags** |
| 花絮区分 | ❌ 无 | ❌ 未知 | ✅ `is_extra` |
| 当前状态 | ✅ **可用** | ❌ **500故障** | ✅ **可用** |

### 结论

- **要精确缺集** → **Web API `local_library?type=tv&tmdb_id=`**（Cookie 鉴权）
- **要批量概览** → **OpenAPI `POST /subscriptions/info`**（配合 TMDB aired 数据）
- **要触发补下载** → **OpenAPI `POST /media/fill_missing`**

---

## 5. 集成建议

### 5.1 推荐工作流

```
1. 定时从 Web API 获取各订阅的缺集
   GET /api/local_library?type=tv&tmdb_id={id}
   → 解析 is_aired=true + has_local=false → 得真缺集

2. 对真缺集调用
   POST /api/openapi/media/fill_missing
   Body: {"tmdb_id": "280049", "media_type": "tv"}
   → "补缺任务已提交队列"

3. 记录补缺历史，避免重复提交
```

### 5.2 Web API Cookie 管理

Cookie 有效期 **30 天**。建议：
- 启动时登录一次，缓存 cookie
- 检测到 401 时重新登录
- 或直接用请求头传 `Cookie: nextmedia_session=xxx`

### 5.3 已知问题

- `local_library/filter` 全线 500 — NextFind 后端 `openapi.py` 的 import bug
- Web API 不走代理（`--noproxy "*"`），直连 `nf.js.248226785.xyz:8443`
- `fill_missing` 只对已订阅剧集有效，不能搜新资源