# NextFind OpenAPI 参考

## 基础信息

- **接口前缀**: `http://<IP>:<端口>/api/openapi`
- **鉴权**: Header `X-API-Key: <密钥>`

---

## 1. 查询

### 全局TMDB搜索
`GET /search`
- 用途：找 TMDB ID 等基础信息
- 参数：`query` (必填), `type` (全部/电影/剧集)

### 搜索网盘与种子资源
`GET /resources/search`
- 用途：查看资源列表，获取各类标签、是否带神盾标志、洗版权重等属性
- 参数：`tmdb_id` (必填), `media_type`, `season`, `episode`

---

## 2. 预览与额度

### 触发探针解包
`POST /preview`
- 用途：一键提取隐藏属性、探针缓存和文件树，帮助分辨文件结构
- 参数：`slug` (资源原始链接或标识)

### HDHive 积分解锁
`POST /hdhive/unlock`
- 用途：消耗积分获取资源真实下载链接
- 参数：`id`, `type`

### 查询额度与积分
`GET /quota`
- 用途：查看当前各个频道的剩余积分、API 次数等状态

---

## 3. 转存与目录

### 一键转存到网盘
`POST /transfer`
- 用途：支持类似 bot 手动转发的 ed2k/磁力或 115 链接的转存
- 参数：可传 `target_folder` 指定绝对转存目录，不依赖系统默认配置

### 查询网盘目录
`GET /directories`
- 用途：获取指定父目录 (传 `cid`) 下的子文件夹列表

### 创建网盘目录
`POST /directories`
- 参数：`parent_cid`, `name`

---

## 4. 删除

### 静默删除指定集
`DELETE /media/episode`
- 参数：`tmdb_id`, `season`, `episode`

### 静默删除整季
`DELETE /media/season`
- 参数：`tmdb_id`, `season`

### 静默删除电影
`DELETE /media/movie`
- 参数：`tmdb_id`

---

## 5. 本地库状态与配置管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/local_library/filter` | 过滤本地库状态，参数 `status_filter` (missing/error/duplicate) |
| GET | `/logs` | 获取系统日志 |
| GET | `/history` | 获取转存历史 |
| DELETE | `/history/all` | 清空全部转存历史 |
| DELETE | `/history/item` | 删除特定历史记录，传 `tmdb_id` 或 `title` 精准删除 |
| GET | `/settings/tg_channels` | 获取 TG 频道 |
| POST | `/settings/tg_channels` | 修改 TG 频道 |
| GET | `/settings/rss` | 获取 RSS 订阅源 |
| POST | `/settings/rss` | 修改 RSS 订阅源 |
| POST | `/settings/rules` | 修改资源过滤规则 |
| POST | `/settings/transfer_folder` | 修改默认转存目录 |

---

## 6. 订阅与追更操作

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/subscriptions/add` | 添加订阅 |
| POST | `/subscriptions/remove` | 取消订阅 |
| GET | `/subscriptions` | 获取活跃订阅列表 |
| POST | `/subscriptions/info` | 批量查询订阅的入库详情和进度 |
| POST | `/media/fill_missing` | 触发补缺集搜索，推入高优搜索队列 |
| POST | `/ignored_episodes/toggle` | 切换忽略季状态 |