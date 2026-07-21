# Emby 刮削器 TMDB ID 错标：根因分析与自动化修复方案

> 供 unisub 实现自动检测+修复功能使用。
> 编写日期：2026-07-19

---

## 一、问题现象

tmdbapi 项目日志中，大量 TV 剧集请求 TMDB 返回 **404**：

```
2026-07-16 23:39:05 - WARNING - TMDB API 请求失败: endpoint=tv/270424 status_code=404
2026-07-16 23:39:05 - WARNING - TMDB API 请求失败: endpoint=tv/283584 status_code=404
...
```

**日志统计（截至 2026-07-19）：**

| 指标 | 数值 |
|------|:----:|
| 日志总行数 | 76,374 |
| 404 发生次数 | **459 次** |
| 负缓存写入次数 | 125 次 |
| 去重 TV ID 数量 | **9 个** |

---

## 二、根因定位

**Emby 刮削器给国产剧/日剧分配了根本不存在的 TMDB ID。**

Emby 自动刮削时，对 TMDB 上不存在的剧集（主要是国产剧和部分日本剧），随机生成了不存在的 ID 写入 `ProviderIds` 字段。tmdbapi 作为代理层，按 Emby 提供的 ID 去请求 TMDB，自然会 404。

**与 TMDB 代理无关。** 即使直连 TMDB API，这些 ID 同样返回 404——不是代理问题，是 ID 本身无效。

---

## 三、影响范围：9 个无效 TV ID

| TMDB ID | 剧名 | 年份 | 类型 | 404 次数 |
|:-------:|------|:---:|:----:|:--------:|
| 120583 | 八仙全传 | 2008 | 国产剧 | 24 |
| 270424 | 舒克贝塔地下之谜 | 2023 | 儿童剧 | 27 |
| 283584 | 异人之下之决战！碧游村 | 2025 | 国产剧 | 27 |
| 310194 | 辉夜大小姐想让我告白 -通往大人的阶梯- | 2025 | 日本剧 | 24 |
| 313473 | 二八杠的夏天 | 2026 | 国产剧 | 24 |
| 314833 | 最浪漫的事 | 2026 | 国产剧 | 27 |
| 318041 | GIFT | 2026 | 日剧 | 24 |
| 321667 | 辉夜大小姐：初吻不会结束 | 2025 | 日本剧 | 24 |
| 1499071 | (未知) | ? | ? | 3 |

> 前 8 个已确认是 Emby 刮削器错误分配的 ID，`tv/1499071` 出现 3 次但未确认。

---

## 四、发现链路（手动流程）

```
tmdbapi 日志 404
  → 提取所有 404 的 TV ID
  → Emby API 查询这些 ID 的 Items（GET /emby/Users/{uid}/Items?ProviderIds=270424）
    → 返回剧集名称、路径
  → 从 Emby 返回的路径中提取 {tmdb-XXXXXX} 文件夹名
  → CloudDrive2 文件系统定位对应文件夹
    → 确认文件夹名中的 {tmdb-xxx} 确实对应 Emby 的 ProviderIds
  → 手动移动文件夹至 待整理 目录
```

### Emby 路径 → CD2 文件夹映射

Emby 的媒体路径如 `/mnt/user/clouddrive/CloudDrive/115open/.../{tmdb-270424}` 与 CD2 的文件系统一致。文件夹名中的 `{tmdb-XXXXXX}` 就是 Emby 写入的 ProviderIds 来源。

---

## 五、当前临时方案

### 5.1 tmdbapi 负缓存

- 对 404 响应写入 **1 小时 TTL** 的负缓存
- 1 小时内不再请求 TMDB，直接返回 404 占位
- 但 1 小时后过期，又会重新请求 TMDB → 再次 404 → 再次写入负缓存
- **治标不治本**：每次过期周期都会浪费 TMDB 配额

### 5.2 手动修复

8 个对应的网盘文件夹已从原路径移至：

```
/mnt/user/clouddrive/CloudDrive/115open/待整理/转存/
```

但 **Emby 中的 ProviderIds 仍然未修正**，如果重新刮削或重新入库，问题会再次出现。

---

## 六、unisub 自动化修复方案

### 6.1 检测逻辑

**核心思路：不读 tmdbapi 日志，不主动扫描全库。unisub 自己请求 TMDB 时，404 当场捕获。**

```python
# 在 TMDBService 中加一层拦截：
# 调用 TMDB API → 返回 404 → 自动写入 emby_blacklist
# 后续同 TMDB ID 的请求直接跳过，不必再试
```

**具体做法：**

对 `TMDBService` 的 `get_tv()` / `get_movie()` 等方法，在收到 404 时：

1. 检查该 ID 是否已在 `emby_blacklist`
2. 如果不在 → 写入黑名单（带来源 "tmdb_404"）
3. 返回 404 给上层调用方

**这样不需要额外定时任务扫描全库。** unisub 正常运行时，只要遇到无效 ID 就会自动记录下来。

**已有基础设施：**
- `emby_blacklist` 表（`models/emby_blacklist.py`）
- `TMDBService` 类（`services/tmdb.py`）——**修改切入点**

### 6.2 修复逻辑（完整流程）

对检测到的无效 ID，完整自动化流程如下：

```
TMDB 返回 404
  → 1. 写入 emby_blacklist（已标记，后续跳过）
  → 2. 查 Emby 获取该 Item 的媒体路径（Path 字段）
  → 3. 路径映射到 CD2 文件系统路径
  → 4. CD2 gRPC API 移动文件夹至 /115open/待整理/转存/
  → 5. （可选）通过 Emby API 清除 ProviderIds.Tmdb
```

#### 步骤 2：Emby 查路径

```
GET /emby/Users/{uid}/Items?Recursive=true&Fields=ProviderIds,Path&Ids={item_id}
```

返回的 `Path` 字段格式如：
```
/mnt/user/clouddrive/CloudDrive/115open/国产剧/舒克贝塔地下之谜 (2023) {tmdb-270424}
```

#### 步骤 3：路径映射规则

Emby 的媒体路径前缀 → CD2 文件系统路径：

| Emby 路径前缀 | CD2 路径 |
|--------------|---------|
| `/mnt/user/clouddrive/CloudDrive/` | `/`（CD2 根目录） |

所以 `.../115open/国产剧/舒克贝塔地下之谜 (2023) {tmdb-270424}` → CD2 中为 `/115open/国产剧/舒克贝塔地下之谜 (2023) {tmdb-270424}`

#### 步骤 4：CD2 gRPC API 移动

**已有基础设施：** `cd2-grpc-api` 技能，CD2 gRPC 客户端已就绪。

```python
# 通过 CD2 gRPC-Web API 移动文件夹
# 认证：gRPC metadata Authorization: Bearer <token>
# 地址：192.168.31.10:19798

# 核心操作流程：
# 1. 获取源文件夹的 FileId（通过 GetSubFiles 遍历）
# 2. 确认目标目录 /115open/待整理/转存/ 存在
# 3. 调用 MoveFile(source_id, dest_dir_id) 或 Rename 更改路径
```

**pass 路径：** `api/cd2-openapi` 存有 CD2 的 API token。

**注意：** 移动前应先确认目标目录存在，不存在则创建。

### 6.3 建议表结构扩展

`emby_blacklist` 表当前字段建议扩展：

```python
class EmbyBlacklist(Base):
    __tablename__ = "emby_blacklist"
    
    id: UUID (PK)
    tmdb_id: int          # 无效的 TMDB ID
    media_type: str       # "tv" | "movie"
    title: str            # Emby 中的剧名（方便识别）
    emby_item_id: str     # Emby 中的 Item ID
    source: str           # "tmdb_404" | "manual"
    detected_at: datetime
    resolved: bool        # 是否已修复
    resolved_at: datetime | None
    notes: str | None     # 备注
```

### 6.4 不需要定时任务
    
**404 自动捕获**已经覆盖了增量场景。但如果想**一次性标记全库已有的无效 ID**（比如首次部署时），可以加一个手动触发的一次性任务：

```
可选：手动触发全库校验
  1. GET /emby/Users/{uid}/Items → 所有媒体项
  2. 对每个有 ProviderIds.Tmdb 的 Item：
     a. 跳过已在黑名单中的
     b. 调用 TMDBService.verify_tmdb_id(tmdb_id, media_type)
     c. 如果 404 → 写入 emby_blacklist
  3. 输出报告：新增无效 ID 列表
```

但这个任务**不是必须的**——不跑全量扫描，404 也会在日常使用中慢慢被捕获。全量扫描只是一个加速器。

### 6.5 关键 API 参考

**Emby Items 查询（含路径）：**
```
GET /emby/Users/{uid}/Items?Recursive=true&Fields=ProviderIds,Path
```

**Emby 更新 Item ProviderIds：**
```
POST /emby/Items/{item_id}/MetadataEditor
Body: { "ProviderIds": { "Tmdb": "" } }  # 空字符串清除
```

**CD2 gRPC-Web API（移动文件）：**
```
地址：192.168.31.10:19798
认证：gRPC metadata Authorization: Bearer <token>
协议：gRPC-Web（非 REST）

核心方法：
  - GetSubFiles(path) → 获取 FileId
  - MoveFile(source_id, dest_dir_id) → 移动
  - Rename(old_path, new_path) → 重命名/改路径
```

> CD2 详细操作指南见 `cd2-grpc-api` 技能（devops 分类）

---

## 七、经验教训

1. **Emby 刮削器不可信。** 对国产剧、小众剧、日本动画/剧集，Emby 经常自动分配随机的 TMDB ID。这些 ID 在 TMDB 上不存在，但 Emby 仍然写入 `ProviderIds`。

2. **负缓存治标不治本。** 1h TTL 的负缓存只能减少 TMDB 请求频率，不能根除 404。——**真正的修复需要从 Emby 侧清除无效 ID**。

3. **文件夹名是线索。** CD2 网盘文件夹名中的 `{tmdb-XXXXXX}` 与 Emby 的 ProviderIds 一致，说明 Emby 的刮削信息来源就是文件夹名本身。如果文件夹名中的 TMDB ID 是错的，Emby 就会把这个错 ID 写进数据库。

4. **手动排查效率低，但自动化可以很轻。** 这 8 部剧集从日志发现 → CD2 定位 → 手动移动，耗时约 40 分钟。但自动化方案不需要定时任务——**在 TMDBService 请求层加一行 404 拦截代码**，所有后续请求自动跳过无效 ID，零额外开销。