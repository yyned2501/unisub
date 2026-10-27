# UniSub Forward 订阅接口 — 对齐 MP 字段 Spec（Rex 消费）

> 状态：**phase 0 实验待做；phase 1 实施待批准**　作者：architect　日期：2026-10-15
> 证据：`docs/rex-moviepilot-api.md`（rev，508 行）、unisub `logs/*`、PG 实测、`services/forward.py` 源码、MP 容器实测

## 0. 先读这条：本 spec 的核心假设**尚未证实**

| 假设 | 状态 | 依据 |
|---|---|---|
| A1「服务端只给 4 键 → Rex 显示不出信息」 | **【已证实】** | `_build_subscribe_item()` 只输出 4 键；DB 里 `poster_url`/`year` 填充 518/524 |
| A2「服务端缺这些键 → Rex 会报错」 | **【已证实·否】** | 49B 全 null 被 Rex 正常消费、2 秒后继续 POST 成功（rev §4.3） |
| A3「补齐 MP 字段 → Rex 就会用、就会变快」 | **【未证实】** | Rex 二进制全文检索 `tmdbid`/`mediaid`/`lack_episode`/`completed_episode` **0 命中**；无可读的 MP 订阅响应模型。是否用 CodingKeys 映射【未证实】（rev U2） |
| A4「Rex 慢是因为它自己补元数据」 | **【推断】** | 逐条拉详情间隔 19–132s 而接口只需 2ms；**无直接证据**证明时间花在 `rex.tmdb` 上 |

**⇒ 铁律：A3 未证实之前，不许把 phase 1 当已批准任务派出去。先做 §1 的 phase 0（零代码改动）。**

## 1. Phase 0 — 决定性实验（零改动，30 秒）

把 **Rex 的服务器地址临时改指向 MP 本体** `http://192.168.31.10:3000`（rev 已证 `NSAllowsArbitraryLoads=True`，任意 http 可指），用 `yangyang` 登录，看订阅列表：

| 结果 | 结论 | 下一步 |
|---|---|---|
| **变快 + 有海报年份** | A3、A4 成立 | 派 phase 1，spec 即终稿 |
| **还是慢 / 还是只有名字** | A3 不成立（Rex 不吃这些字段） | **停止 phase 1**，转 rev §9.2 实验 2：mock 逐级剥离字段，定位 Rex 真实解码边界 |

**注意**：MP 列表 81 条、unisub 459 条 —— **只评估「快不快、全不全」，不评估条数**。

**更省事的触发方式**（rev 从二进制挖出的调试入口，不用翻 UI）：`检查订阅` / `切换订阅` / `模拟订阅钩子流`。

## 2. 背景

Rex（iOS，自称使用 MoviePilot REST API）订阅列表**只显示名字**、**很久才加载出信息**；同数据的 forward App 很快。

| 事实 | 证据 |
|---|---|
| forward 与 Rex 走**同一段代码、同一份数据** | 都走 `GET /api/v1/subscribe/user/{username}` → `list_subscribes()` → `_build_subscribe_item()` |
| 该函数只输出 **4 键** | `services/forward.py:38-58` |
| 海报/年份**早在库里** | PG 实测 524 条：`poster_url` 518（98.9%）、`year` 518（98.9%） |
| 服务端毫秒级 | 列表 459 条 5–29ms、详情 1–4ms |
| unisub **没有**转发 MP | MP 日志 144 条来自 .8 的请求全由 `MoviePilotService` 镜像逻辑产生 |
| Rex 响应形状**已被字节级复现** | 49/75/63/62/57/185B 六项逐字节吻合（rev §4.1） |
| MP 容器**支持** `/subscribe/user/{username}` | 实测 200/98729B/43 键；**官方源码 v1.0.0→main 无此路由** → 你跑的是扩展版（rev §7） |
| Rex 侧配置面已证实 | 服务器地址/启用开关/同步移除订阅开关/账号密码；凭据存 Keychain（rev §3.1） |
| gzip 陷阱 | 列表 12064B 是**压缩后**，不能反推字段数（rev §4.4） |

## 3. 组件边界

| 项 | 说明 |
|---|---|
| 改动文件 | `backend/app/services/forward.py`（**唯一改动点**，phase 1） |
| 数据源（只读） | `subscriptions`（`nf_status='active'`）+ `emby_cache`（按 `tmdb_id` LEFT JOIN） |
| 有状态 | **无**（纯读+序列化，无缓存/写/外部调用） |
| 不碰 | `orchestrator`、`MoviePilotService` 镜像链路、NextFind 推送、DB schema、其他 router |
| 性能 | 列表路径**禁止**逐条外部查询；只允许 **1 次 SQL** |

## 4. 接口契约

| 端点 | 用途 | 现状 | 要求 |
|---|---|---|---|
| `GET /api/v1/subscribe/user[/{username}]` | Rex 列表 | 4 键 | 补键；p95<100ms；≤250KB |
| `GET /api/v1/subscribe/` | forward 列表（**Rex 未用**） | 4 键 | 同上 |
| `GET /api/v1/subscribe/media/{mediaid}[?season=N]` | Rex 详情 | 4 键 | + `description`；未命中**仍返回 49B 全 null 对象** |

**兼容性铁律（rev §4.3-4 逐字采纳，优先级最高）**：

1. **加新键安全**（Swift `JSONDecoder` 默认忽略未知键）；
2. **绝不能改既有键的类型**（`tmdbid` int→string、`name` string→number 会真踩解码失败）；
3. **绝不能把 `null` 换成 `0`/`""`**；
4. **不能把未命中的 49B 改成 404** —— 会把「未订阅」变成「请求失败」，触发 Rex 的 `request failed (HTTP %lld)` 文案；
5. `type` 保持中文 `"电影"/"电视剧"`（rev 已证与官方 MP `MediaType` 枚举**完全一致**，非缺陷）。

**事实校准**：MP 响应是**裸数组**（`[{...}]`），不是 `{data:[...]}`；unisub 现状一致 → 保持。

## 5. 数据格式（对齐 MP 实测 · 43 键）

MP 容器实测单条（`GET http://192.168.31.10:3000/api/v1/subscribe/user/yangyang`，X-API-Key 鉴权）：

```json
{"id":1811,"name":"汪汪队立大功","year":"2013","type":"电视剧","keyword":null,"tmdbid":57532,
 "doubanid":null,"bangumiid":null,"anilistid":null,"mediaid":null,"media_source":"themoviedb",
 "media_id":"57532","season":14,"poster":"https://image.tmdb.org/t/p/w500/….jpg",
 "backdrop":"…","vote":7.0,"description":"…","filter":null,"include":null,"exclude":null,
 "quality":null,"resolution":null,"effect":null,"total_episode":19,"start_episode":0,
 "lack_episode":19,"completed_episode":0,"note":null,"state":"R","last_update":"2026-10-06 13:43:10",
 "username":"yangyang","sites":null,"downloader":null,"best_version":0,"best_version_full":0,
 "current_priority":null,"episode_priority":null,"save_path":null,"search_imdbid":0,
 "date":"2026-08-02 00:43:53","custom_words":null,"media_category":null,"filter_groups":null,
 "episode_group":null}
```

**类型铁律**：`year` = **字符串**；`vote` = float；`state` = 字符串（实测 `"R"`）；`last_update`/`date` = `"%Y-%m-%d %H:%M:%S"`；`best_version`/`best_version_full`/`search_imdbid` = **int**（`0`，非 bool）；缺失字段给 **`null`**（不是 `""`、不是省略键）。

| MP 字段 | 类型 | unisub 来源 |
|---|---|---|
| `id` | int | **保持 = `tmdb_id`**（风险登记 §7.3） |
| `name` | str | `subscriptions.title` |
| `year` | **str** | `str(subscriptions.year)` |
| `type` | str | `media_type` → `"电影"/"电视剧"` |
| `tmdbid` | int | `subscriptions.tmdb_id` |
| `media_source` | str | 常量 `"themoviedb"` |
| `media_id` | str | `str(tmdb_id)` |
| `poster` | str/null | `poster_url`（空则回落 `emby_cache.poster_url`） |
| `state` | str | `nf_status`：`active→"R"`、`missing_fill→"N"`、`completed→"P"` |
| `last_update` / `date` | str | `updated_at` / `created_at` |
| `lack_episode` | int | `nf_missing_eps` |
| `total_episode` | int/null | `emby_cache.tmdb_total_eps` |
| `completed_episode` | int | `0` |
| `start_episode` | int | `0` |
| `username` | str | `auth_config.json` username |
| `description` | str/null | `emby_cache.overview`（**仅详情**，见 §6） |
| `season` | int/null | **无来源 → null**（§7.1） |
| 其余 21 键 | null | 无来源 → `null`（**键必须存在**） |
| `best_version`/`best_version_full`/`search_imdbid` | int | `0` |

**禁止**：把 null 写成 `""`/`0` 冒充；改既有键的类型。

## 6. 量级约束

| 项 | 值 |
|---|---|
| 列表条数 | 459（上限按 1000） |
| 响应体积 | 现 54KB → **≤250KB** |
| **体积红线** | `description` **不得进列表路径**（459×300–800 字会到 MB 级） |
| 列表 SQL 次数 | **1 次**，禁止逐条 |
| 服务端耗时 | p95 < 100ms |
| 客户端 | iOS 蜂窝网络；详情必须保持毫秒级 |

## 7. 范围（**需主人拍板**）

### 7.1 本期提案：只做「补齐展示键」

`season` 一律返回 `null`、行为不变。**理由**：唯一能靠纯映射零风险完成的改动（数据全在库里，不建表、不查外部）。

### 7.2 🔴 待决策：rev 发现的真缺陷（**均【已证实】**，比补字段更影响正确性）

| # | 缺陷 | 后果 | 修的代价 |
|---|---|---|---|
| **C2** | `DELETE ...?season=N` 丢弃 season，**按 tmdbid 删整部** | **按季退订会删掉整部剧** — 数据破坏级 | **实测降级 → 不用动 schema，见 §7.2.1** |
| **C1** | `GET ...?season=N` 忽略 season | 多季剧「未订阅第 2 季」时**误报已订阅** | **同 §7.2.1** |
| **C4** | 列表只回 `active` | 库里另有 **37 completed + 28 NULL**，在 Rex 里显示「未订阅」而服务端认定「已订阅」→ 状态自相矛盾 | 放宽过滤或加 `?status=`；需先确认 Rex 怎么用列表 |
| **C6** | 本地无记录的 DELETE 返回 `success:false` | 官方恒 `success:true`（幂等）；unisub 会失败 | 小改 |
| **C5** | `POST /subscribe/` 不收 `season` | 剧集订阅无法表达季号 | 随 C1/C2 一起 |
| **C7** | `id` = tmdbid（非订阅主键） | 若 Rex 用 `data.id` 调 `/subscribe/{id}` 会错 | 风险【未证实】，待 rev 实验 1 抓 body |

### 7.2.1 实测修正：C1/C2 **不需要** DB schema 变更

rev §8 建议「给 `Subscription` 加 season 维度、键改 `(tmdb_id, season)`，波及 459 条」—— **实测数据不支持这个成本估计**。unisub 内部**早已有按季模型**：

| 已有资产 | 现状 |
|---|---|
| `mp_subscription` 表 | **322 行 / 275 订阅 / 185 行带季号 / 18 种季号**；`Index(subscription_id, season, UNIQUE)`；表注释即「（MP 订阅粒度按季），故用独立子表存储」 |
| 按季查询能力 | `MoviePilotService.find_subscription(tmdb_id, season=None)`（**已支持按季**）、`mp_missing.diff_missing()` |
| 按季数据源 | `tmdb_season`（已播集数）、`emby_season_cache`（库内集数） |
| 前端 | `SubscriptionsView.vue` 已在渲染 `MP 3季 缺5` / `S2 缺3` |

**真正的缺口只在 `routers/forward.py` 的接线**：

```python
# routers/forward.py:233  收了 season …
season: int | None = Query(None, description="季号"),
…
return await svc.remove_subscribe(db, int(raw))   # ← season 没传下去
```

`remove_subscribe(db, tmdb_id)` 只查主表 `Subscription.tmdb_id == tmdb_id` → `orchestrator.unsubscribe(db, sub.id)`（删**整条**订阅）。

**⇒ 修 C1/C2 的正确做法是「把 season 透传到已有的 `mp_subscription` 子表」，不是加 schema 维度。工作量：路由层 + service 层各一处，不动表结构、不波及存量 459 条。**

**⚠️ 唯一需要主人定义的语义**（架构决策，非实现细节）：Rex 发 `DELETE .../tmdb:303060?season=1` 时——

| 方案 | 行为 |
|---|---|
| **S-A**（架构师建议） | 只退该季：删/停 `mp_subscription` 中 `(tmdb_id, season=1)` 那条，**主订阅保留** —— 与官方 MP 语义一致（官方=按 tmdbid+season 删记录） |
| **S-B** | 退该季且当它是最后一季时连带退整剧 |

**规模参考**：tv 订阅 322 条，其中总集数 >30 的 **93 条**（多季剧强候选），最大 1464 集。

**架构师意见**：C2（按季退订删整部剧）是**数据破坏级**，优先级高于「补字段让 UI 好看」；且经 §7.2.1 实测，**它比想象中便宜**（路由接线，不动 schema）。**仍建议先做 §1 phase 0 实验**确认补字段的价值，再定 phase 1 与 C2 的先后。

### 7.3 非目标

1. 不做 MP 转发代理（数据源必须仍是 unisub 的 459 条，不是 MP 的 81 条）；
2. 不改 `id` 语义（rev U3：**无证据** Rex 拿 `id` 调 `/subscribe/{id}`；改了反有删错风险）；
3. 不改 MP 镜像链路、不补 `vote`/`backdrop`/片源类假值、不动 DB schema。

**已登记风险**：`id` 冒充 tmdbid —— 若将来某客户端用 `DELETE /subscribe/{id}` 语义会删错。待 rev §9.2 实验 1（nginx 临时记 `$request_body`）验证。

## 8. 验收（三动作）

1. **接口对契约测**：`curl` 列表+详情 → 断言 §5 全部 43 键存在、类型正确（`year` 字符串、`vote` float）；抽 3 条与 PG 比对（`poster`==`poster_url`、`year`==`str(year)`、`lack_episode`==`nf_missing_eps`）；未命中仍是 49B。
2. **数据流对设计查**：列表 SQL 仅 1 次；体积 <250KB；p95 <100ms；`description` 不在列表里。
3. **边界对假设问**：`poster_url`/`year` 为 null 的 6 条不报错；`emby_cache` 无匹配不丢条；非 active 不出现。
4. **端到端**：phase 0 实验给出答案（见 §1）。

## 9. 交付物

- `backend/app/services/forward.py` 改动（类型注解 + 中文 docstring，遵守 `backend/app/STANDARDS.md`）
- 重启后端 + `curl` 实测贴证（字段/体积/耗时）
- 单文件 <300 行（现 272 行）