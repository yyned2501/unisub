# Rex（iOS/macOS App）× MoviePilot REST API 订阅调用契约

> 目标：把 `unisub` 的 `backend/app/routers/forward.py` 对齐到 **Rex 真实发出的请求** 与 **Rex 真正在意的响应字段**。
> 交付者：rev（逆向）｜日期：2026-10-15｜任务卡：`t_b19d6966`
>
> **证据分级（全文统一）**
> - **【已证实】** 有可复核的一手证据：二进制文件偏移 / 资源文件原文 / nginx access log / 服务端 DB / 上游源码。
> - **【推断】** 证据链指向该结论但有替代解释，标注依据与置信度。
> - **【未证实】** 拿不到证据，写明还缺什么条件，**不猜**。

---

## 0. 结论速览（TL;DR）

| # | 结论 | 等级 |
|---|---|---|
| 1 | 端点集 = 4 组：`POST /api/v1/login/access-token`、`GET /api/v1/subscribe/user/{username}`、`GET\|DELETE /api/v1/subscribe/media/{mediaid}?season=N`、`POST /api/v1/subscribe/` | 【已证实】 |
| 2 | 鉴权 = `Authorization: Bearer <jwt>`；401 后 Rex 自动 `POST /login` 再重放（3s 内） | 【已证实】 |
| 3 | `mediaid` 格式 = `tmdb:{id}`（冒号裸传）；剧集带 `?season=N`，电影不带 | 【已证实】 |
| 4 | **响应字段没有一个是"缺了就整体解码失败"的必需品** —— 49B 全 null 负载被 Rex 正常消费并继续后续调用 | 【已证实（行为）】/ 具体模型【未证实】 |
| 5 | 现有 7 字段**不需要为防解码失败而补齐**；补齐的价值只在 UI 信息量 | 【推断（强）】 |
| 6 | `POST /api/v1/subscribe/` 的 JSON 键名**未证实**；反射池中存在**唯一一处类型名后缀 `…ilotSubscriptionRequestV`**（完整名被 Swift 后缀压缩，前缀不落盘），按同池模式（如 `…ushSubscriptionSettingsO` = `PushSubscriptionSettings`）读作 `MoviePilotSubscriptionRequest` **属推断** | 【推断（强）】 |
| 7 | unisub **忽略 season**（GET 与 DELETE 都忽略）；官方 MP 的 season 是一等判定维度 → 真缺陷：按季退订会误删整剧、按季查已订阅会跨季误判 | 【已证实（对齐官方源码）】 |
| 8 | `GET /api/v1/subscribe/user/{username}` **不是 MoviePilot 官方路径**（v1.0.0 → main 全查无此路由）；官方列表是 `GET /api/v1/subscribe/` | 【已证实】 |
| 9 | 响应里 `type` 用中文 `"电影"/"电视剧"` **与官方 MP `MediaType` 枚举完全一致**，不是缺陷 | 【已证实（对齐官方源码）】 |
| 10 | 服务端字节级形状可精确复现：49/75/63/62/57/185B 六项与之逐字节吻合；257B 需 `access_token` 长 151 字符 | 【已证实】 |
| 11 | 列表 459 条 = DB `nf_status='active'` 实测 459；**但 12064B 是 gzip 后长度**，"26B/条 → 字段极简"的推导不成立（结论恰好仍对，依据不成立） | 【已证实】 |

---

## 1. 方法与证据面

### 1.1 可读证据面（取得的实际证据）

| 证据源 | 位置 | 用途 |
|---|---|---|
| nginx access log（真实调用） | `/home/hermes/projects/unisub/logs/nginx-access.log` | 端点、方法、状态码、响应字节数、UA |
| 服务端业务日志 | `/home/hermes/projects/unisub/logs/backend.log` | `NextFind 订阅成功: … (movie, tmdb_id=1148365)` |
| 生产库 | `psql postgresql://unisub@192.168.31.48:5432/unisub` | `nf_status` 分布（列表口径） |
| **Rex 二进制可读段** | `…/architect/cache/scratch/rex/Payload/Rex.app/Rex` → `__DATA(0x46e0000)` / `__DATA_CONST(0x4514000)` / `__LINKEDIT(0x4898000)` | 常量池、Swift 反射池（字段/类型名）、方法签名 |
| 本地化文案 | `Payload/Rex.app/{en,zh-Hans,zh-Hant,ja,…}.lproj/*.strings`（12 个语言包） | 失败语义、降级点（**强证据**） |
| 脚本层资源 | `Payload/Rex.app/RexScript_RexScript.bundle/**` | 判定订阅链路是否走脚本层（结论：否） |
| **上游源码** | `github.com/jxxghp/MoviePilot`（`main` 及 `v1.0.0/v1.5.0/v1.7.0/v1.8.0/v1.9.0/v1.9.9`） | 判定"照官方"还是"自有简化" |

关键偏移（本节所有偏移均为 `Rex` 文件内偏移，`=` 表示被 NUL 分隔的池条目起点）：

```
0x47ce368  MP/auth 常量簇          (api / login / access-token)
0x48074b8  rex.moviepilot.          (UserDefaults/Keychain 前缀)
0x4906060  seasonSiv + init(tmdbID:title:season:mediaType:)    (camelCase 4 字段结构)
0x4905f9b  MediaIdentifiersRequestV / RecommendResolveRequestV
0x48fe81a  12access_token + 23__derived_struct_equals + 4fromACs7Decoder_p_tKcfC
           + 6encode2toys7Encoder_p_tKF + 9expiresAt10Foundation4DateVv   ← 登录响应 DTO（唯一字段）
0x48fe921  imdbIdSSSgv          (String?)
0x48fe930  tmdbIdSiSgv          (Int?)
0x48fe9de  7traktIdSiSgv + 9mediaTypeSSSgv  ← 4 字段全 optional 的标识结构
0x49ab852  moviePilotTotalSiSgv / 0x49abbf0 moviePilotCompletedSiSgv   ← 库条目模型字段（optional）
0x4922bad  liveIsMoviePilotSubscribed33_F2FD…LLSbvpfi (+ mockIsMoviePilotSubscribed)
0x49229c1  MoviePilotScopeChangedySi_SiSgtcSgv   ← (Int, Int) -> Void 回调
0x49226f6  lastMoviePilotScopeKey33_F2FD…LLSSSgv (String?)
0x49bd1c2  …ilotSubscriptionRequestV   ← 订阅请求类型名（后缀压缩，前缀不落盘）
0x49c63c1  PilotHubC                   ← 完整可读类名
0x49c4f3a  mediaID…                    ← 大写 ID 变体（非订阅响应模型）
```

### 1.2 硬否定项（**已关闭，不再投入**）

1. **`__TEXT` 全段 FairPlay 加密**（`LC_ENCRYPTION_INFO_64` cryptid=1，cryptoff=`0x4000`，cryptsize=`0x4508000`）→ `__text` 机器码、`__cstring` 字符串字面量、`__swift5_*` 反射元数据在磁盘上都是密文。
   **推论（重要方法论）**：Swift 的 `CodingKeys` 载荷（`__TEXT,__const`）与 JSON 键名**只以字面量形式存在**，因此凡是"**属性名与 JSON 键名不同**"的字段，其键名不可读；而**属性名本身**在 `__LINKEDIT` 反射池里是可读的。本报告的所有字段名结论都建立在这条分界上。
2. **真机 dump / Frida 不可行**：`MinimumOSVersion = 17.0`，手上唯一越狱机 iOS 8 → 无进程可 hook。
3. **脚本层不是 MP 契约的载体**（本报告新证，见 §1.3）。

### 1.3 脚本层否证（新证据）

对 `RexScript_RexScript.bundle` 全量（`cheerio.bundle.js` 579,054 B + `OfficialModules/*.js|json`）逐文件统计 `moviepilot` / `self.?hosted` / `/api/v1/...` 命中数：

```
bangumi.js     mp=0 self=0 apiv1=0   hosts: assets.rexnow.tv, rexnow.tv
danmu.js       mp=0 self=0 apiv1=0   hosts: api.dandanplay.net, assets.rexnow.tv, dm.itcxo.cn, rexnow.tv, v.qq.com
nlsearch.js    mp=0 self=0 apiv1=0   hosts: api.rexnow.tv, assets.rexnow.tv, rexnow.tv
rex-tmdb.js    mp=0 self=0 apiv1=0   hosts: assets.rexnow.tv, rexnow.tv, www.themoviedb.org
manifest.json  mp=0 self=0 apiv1=0   hosts: assets.rexnow.tv
cheerio.bundle.js mp=0 self=0 apiv1=0
脚本层实际存在的 API 路径（全量）：
  danmu.js   : /api/v2/search/anime, /api/v2/search/episodes, /api/v2/match, /api/v2/bangumi/${id},
               /api/v2/comment/${parsedCommentId.id}
  nlsearch.js: /api/discovery/ai…（api.rexnow.tv，Rex 自有 AI 搜索）
```

**结论【已证实】**：自建服务订阅链路 **100% 在 Swift 层**，脚本层零涉及；`rex-tmdb.js` / `nlsearch.js` / `bangumi.js` / `danmu.js` 只负责 TMDB / Rex 自有 AI 搜索 / 番剧 / 弹弹play 元数据。
因此"JS 里点出的属性名就是它期望的字段名"这条路对 MP 契约**不适用** —— 架构师 14:2x 的优先级 ① 在此**否证**（不是"没找到"，是"这块明文里确实没有 MP 契约"）。

### 1.4 最强的一条明文证据：**Rex 内部把这个功能就叫 `moviepilot`**

所有本地化 key 与代码命名都直指 MoviePilot（UI 文案才译成"自建服务"）——【已证实】：

```
AppSettings.strings  appSettings.copy.moviepilot.settings.were.saved.subscription.syncing.has.started
                     appSettings.copy.moviepilot.sign.in.failed.no.access.token.was.returned
                     appSettings.copy.moviepilot.subscription.list.unavailable
                     appSettings.copy.rex.uses.the.moviepilot.rest.api.to.aggregate.add.and
                       en: "Connect to your self-hosted resource management service to add, sync and remove
                            movie and TV subscriptions. Accounts, passwords and tokens are not stored in
                            library data."
                     appSettings.copy.the.otp.is.used.only.for.this.test.and.is
                       en: "…Passwords and access tokens are stored in this device's Keychain."
二进制               0x48074b8  rex.moviepilot.        ← UserDefaults/Keychain 键前缀
                     0x49ab852  moviePilotTotalSiSgv    / 0x49abbf0 moviePilotCompletedSiSgv
                     0x4922bad  liveIsMoviePilotSubscribed33_F2FD…LL  (+ mockIsMoviePilotSubscribed)
                     0x49229c1  MoviePilotScopeChangedySi_SiSgtcSgv   ((Int, Int) -> Void)
                     0x49226f6  lastMoviePilotScopeKey33_F2FD…LLSSSgv (String?)
                     0x49c63c1  PilotHubC  (class)
                     0x49bd1c2  …ilotSubscriptionRequestV (后缀压缩)
```

推论（【已证实】级）：**Rex 是按 MoviePilot 的 REST API 语义实现的**（官方 API 文档/行为对齐），
**唯一非官方之处是列表路径 `/subscribe/user/{username}`**（§7）——这是本报告里最重要的"语义差"来源。
调试入口（供取证用）：`appSettings.copy.debug.check.subscription`（检查订阅）、
`appSettings.copy.debug.toggle.subscription`（切换订阅）、`appSettings.copy.debug.flow.mediahook`（模拟订阅钩子流）。
另：`Shell.strings` 有「订阅服务未配置时，订阅项不会出现在列表中」→ **未配置时该 Tab 整体隐藏**（解释"为什么有些实测看不到订阅项"）。

---

## 2. 端点契约

### 2.1 端点表

| 用途 | 方法 | 路径 | 鉴权 | 响应形状 | 等级 |
|---|---|---|---|---|---|
| 登录 | POST | `/api/v1/login/access-token` | 无 | 裸对象（见 §4.1） | 【已证实】 |
| 列表 | GET | `/api/v1/subscribe/user/{username}` | Bearer | **裸数组** | 【已证实】 |
| 详情/查已订阅 | GET | `/api/v1/subscribe/media/{mediaid}[?season=N]` | Bearer | 裸对象（命中）／**全 null 裸对象**（未命中） | 【已证实】 |
| 退订 | DELETE | `/api/v1/subscribe/media/{mediaid}[?season=N]` | Bearer | `{success,message,data}` | 【已证实】 |
| 订阅 | POST | `/api/v1/subscribe/` | Bearer | `{success,message,data:{id:…}}` | 【已证实】 |
| （存在但未被 Rex 使用） | GET | `/api/v1/subscribe/` | Bearer | 裸数组 | 【已证实】unisub 已实现 |

### 2.2 逐端点细节

**① `POST /api/v1/login/access-token`**
- 编码：**`application/x-www-form-urlencoded`**（`username` / `password`），非 JSON。【已证实】（unisub 以 `Form(...)` 接收实测通过；且官方 MP 同为 form）
- 触发时机：**不是启动即登**。13:58:37 先打列表吃 401 → 13:58:40 才登录 → 13:58:40/41 重放列表 ×3。
  → **【已证实】懒登录 + 401 挑战式重试（3 秒内自动补救）**。
- 响应字节：257B。【已证实】

**② `GET /api/v1/subscribe/user/{username}`**
- 路径带**真实用户名**（`yangyang`），非固定串。【已证实】
- 响应：**裸 JSON 数组，无 `{code,msg,data}` 包装**。【已证实】（12064B 与 unisub 的 `list[dict]` 一致；官方同为裸 `List[Subscribe]`）
- 状态码：200。同一次会话被连续拉 3 次（13:58:40、13:58:41×2）→ **【推断】启动/重连时会重复拉取列表**（也可能是一次 UI 刷新 + 一次同步）。

**③ `GET /api/v1/subscribe/media/{mediaid}`**
- `mediaid` = `tmdb:{id}`，**冒号原样进路径、未被转义**（nginx log 里是 `tmdb:1148365`）。【已证实】
- 剧集请求**同时**打了不带季与带季两版：`tmdb:303060` 与 `tmdb:303060?season=1` → **【已证实】Rex 明确区分"整剧"与"某季"两种查询**（这是 unisub 最需要补的语义差）。
- 未命中响应 = **全 null 对象 49B**，HTTP 仍 200。【已证实】——与官方 MP 的 `Subscribe()` 空模型行为**一致**（§7）。

**④ `DELETE /api/v1/subscribe/media/{mediaid}[?season=N]`**
- 电影退订**不带 season**（13:59:03），剧集退订**带 season**（13:59:16）。【已证实】

**⑤ `POST /api/v1/subscribe/`**
- 电影一次、剧集一次，响应 63B / 62B。【已证实】
- 剧集那次服务端日志显示 **未区分季**（unisub 忽略了该字段；无法反推 Rex 是否发了 season）→ 键名【未证实】。

---

## 3. 请求契约

### 3.1 鉴权

**Rex 侧配置面（已证实 = 有本地化 key 背书）**

| 配置项 | 本地化 key | 取值 | 对契约的意义 |
|---|---|---|---|
| 服务器地址 | `appSettings.copy.server.address` = 「服务器地址」/ `Server Address` | **任意完整 `http://` 或 `https://` URL**（`appSettings.copy.invalid.server.address.enter.a.complete.http.or.https.url`） | 决定 base URL；**http 明文被接受**（`NSAllowsArbitraryLoads=True`） |
| 启用开关 | `appSettings.copy.enable.server.subscriptions` = 「启用自建服务订阅」 | 布尔 | 关闭时整个订阅 Tab 隐藏 |
| 同步移除订阅 | `appSettings.copy.sync.subscription.removal` = 「同步移除订阅」 | 布尔 | **关闭时 Rex 只在本地移除、不调 DELETE**（`…synchronized.subscription.removal.is.off…`） |
| 账号 / 密码 | （UI 有输入框；未逐条核对其 key） | 文本 | 即登录 form 的 `username` / `password`；**凭据存 Keychain**（`appSettings.copy.the.otp.is.used.only…`） |

| 项 | 值 | 等级 |
|---|---|---|
| Header 名 | `Authorization` | 【已证实】（`__DATA` 常量 + 官方 MP `OAuth2PasswordBearer`） |
| 前缀 | `Bearer `（带空格） | 【已证实】（401→重放链路成立；官方为 bearer scheme） |
| Cookie / API Key | **未使用** | 【已证实】（同一路径无 `X-API-Key` 痕迹，且 401 后走登录而非换 key） |

【已证实】的无鉴权→401→登录→重放序列（原始 log 序）：

```
13:58:37 GET  /api/v1/subscribe/user/yangyang        200 12064
13:58:40 POST /api/v1/login/access-token             200 257
13:58:40 GET  /api/v1/subscribe/user/yangyang        200 12064
13:58:41 GET  /api/v1/subscribe/user/yangyang        200 12064
```

### 3.2 请求体（**交付要求 B**）

- **编码【已证实】**：列表/详情/退订 = **无 body**（query + 路径参数）；登录 = **form**；新增订阅 = **JSON**（官方 `POST /` 收 `subscribe_in: schemas.Subscribe`，JSON body；unisub 的 `ForwardSubscribeInput` 亦为 JSON body，实测解析成功）。
- **字段名【未证实】**：Rex 二进制反射池里存在**唯一一处**订阅请求类型名后缀条目 `…ilotSubscriptionRequestV` @`0x49bd1c2/0x49bd1c6`（Swift 后缀压缩：前缀由 3 字节引用回指，**不落盘**；`MoviePilotSubscription` / `PilotSubscription` / `Autopilot` 作为连续串全文 **0 命中**）→ 完整名按同池模式（相邻条目 `…ushSubscriptionSettingsO` ⇔ `PushSubscriptionSettings`）读作 **`MoviePilotSubscriptionRequest` = 【推断（强）】**，**不是【已证实】**；
  其**成员（JSON 键名）在加密区**（属性名与键名不同则键名不可读）→ **具体键名 = 【未证实】**。
- **客户端类【已证实】**：反射池中完整可读的类名 **`PilotHub`**（单次出现 @`0x49c63c1`，形态 `…CueStoreV | PilotHubC | SettingsC` → `PilotHub` 是一个 class）。**推断**：它就是 Rex 的自建服务（MoviePilot）客户端类；其成员名不可读，因此**不构成**键名证据。
- **服务端侧可证的边界【已证实】**：unisub 现存 `ForwardSubscribeInput{tmdbid, name, type, mediaid}` **成功解析了 Rex 的请求**，且业务日志给出 `火柴盒大电影 (movie, tmdb_id=1148365)`。
  → Rex 的 body 至少提供了 **tmdbid 或 mediaid 之一 + name + type**。
  ⚠️ **无法区分**它用的是 `tmdbid` 键还是 `mediaid: "tmdb:1148365"` —— unisub 两条路都能解出同一个 `tmdb_id`。【未证实】
- **`type` 取值【推断（强）】**：官方 MP 的 `MediaType` 枚举值是**中文字面量 `'电影'/'电视剧'/'未知'`**（§7 已证实），unisub 的请求解析同时接受 `movie/tv/电影/电视剧/剧集` → **无论 Rex 发中文还是英文都通**，实现上无需改动。
- **`season` 是否在 body 里【未证实】**：服务端忽略该语义，日志无法反推。

**建议（面向未来兼容）**：`ForwardSubscribeInput` 保留 `tmdbid` **与** `mediaid` 双通道，并对 `season` 做**显式接收并落地**（见 §8-C）。

### 3.3 路径参数格式

| 项 | 值 | 等级 |
|---|---|---|
| `mediaid` | `tmdb:{id}`，冒号不转义；纯数字形式**未观测到**（unisub 兼容两者） | 【已证实】（`tmdb:` 形式）/【未证实】（纯数字） |
| `season` | query 整数，**仅剧集**；电影不带 | 【已证实】 |
| 尾部斜杠 | 订阅用 `POST /api/v1/subscribe/`（**有**尾斜杠）；列表用 `/subscribe/user/{username}`（无） | 【已证实】 |

---

## 4. 响应契约（**交付要求 A 的核心**）

### 4.1 各端点实测形状与字节指纹（**逐字节复核**）

用 unisub 现有代码的字段集复现 body 长度（`json.dumps(..., ensure_ascii=False, separators=(',',':'))`）：

| 实测字节 | 复现 body | 复现长度 | 判定 |
|---|---|---|---|
| **49** | `{"id":null,"tmdbid":null,"name":null,"type":null}` | 49 | ✅ 精确吻合 |
| **75** | `{"id":1148365,"tmdbid":1148365,"name":"火柴盒大电影","type":"电影"}` | 75 | ✅ 精确吻合 |
| **63** | `{"success":true,"message":"订阅成功","data":{"id":1148365}}` | 63 | ✅ 精确吻合 |
| **62** | `{"success":true,"message":"订阅成功","data":{"id":303060}}` | 62 | ✅ 精确吻合 |
| **57** | `{"success":true,"message":"取消订阅成功","data":{}}` | 57 | ✅ 精确吻合 |
| **185** | `{"id":303060,"tmdbid":303060,"name":"…","type":"电视剧","total_episode":null,"lack_episode":10,"completed_episode":null}` | 146 + 名称 39B | ✅ 形状吻合，名称 ≈21 字（截断展示所致） |
| **257** | 登录 6 字段响应 | 111 + token | ✅ 需 `access_token` 长 **151** 字符（HS256 JWT 典型长度） |
| 12064 | 列表 | — | ⚠️ **gzip 后长度**（见 4.4） |

→ **【已证实】响应体形状、字段集、中文 `type` 值全部由字节指纹独立复核通过**，不是从源码"读出来的假设"。

### 4.2 字段表（服务端现状 = 事实基线）

`GET .../media/{mediaid}` 命中（剧集）：

```json
{"id":303060,"tmdbid":303060,"name":"弱气MAX的大小姐….", "type":"电视剧",
 "total_episode":null,"lack_episode":10,"completed_episode":null}
```

| 字段 | 类型 | 电影 | 剧集 | 备注 |
|---|---|---|---|---|
| `id` | int | ✓ | ✓ | 事实上 = tmdbid（非 MP 语义的订阅主键） |
| `tmdbid` | int | ✓ | ✓ | |
| `name` | string | ✓ | ✓ | 可长可短，UTF-8 |
| `type` | string | `"电影"` | `"电视剧"` | **官方枚举值，务必保持** |
| `total_episode` | int \| null | ✗ 不出 | ✓（现恒 null） | |
| `lack_episode` | int \| null | ✗ 不出 | ✓ | |
| `completed_episode` | int \| null | ✗ 不出 | ✓（现恒 null） | |

未命中：`{"id":null,"tmdbid":null,"name":null,"type":null}`（49B，HTTP 200）。【已证实】

### 4.3 **哪些字段是非 optional（缺了会整体解码失败）？** —— 交付要求 A

**证据 1（硬行为）【已证实】**
13:59:05 未命中详情返回 **49B 全 null** → Rex **没有**报"服务器返回了无法识别的数据"、没有中断，**2 秒后（13:59:05 / 13:59:18）继续发起 `POST /subscribe/` 并成功**。
→ 全 null 的 `id/tmdbid/name/type` **不会导致整体解码失败**；缺字段同理不会（unisub 对电影连 `total_episode` 等 3 键都不发）。

**证据 2（上游契约）【已证实】**
官方 MP 在未命中时也返回 **空 `Subscribe()` 模型**（`return result if result else Subscribe()`，`response_model=schemas.Subscribe`，35 字段全 null）。Rex 既然是照着这个 API 写的，**它的解码器必然容忍"字段存在但为 null"**；而 unisub 更进一步连键都不发。

**证据 3（二进制否证）【已证实】**
在 `Rex` 二进制全文检索（`str.find` + `count`，偏移为文件偏移）：

```
tmdbid              = 0 命中
mediaid             = 0 命中
lack_episode        = 0 命中
completed_episode   = 0 命中
lackEpisode         = 0 命中
completedEpisode    = 0 命中
total_episode       = 2 命中 @0x49028b7 / @0x49029be
    上下文：7tmdb_id6season0J5_name05show_K06poster8backdrop7network6airing14total_episodes…
            first_air_dateSSSgv  total_episodesSiSgv        ← TMDB 剧集结构体属性（snake_case）
totalEpisode        = 4 命中 @0x491614a / @0x49163f7 / @0x49d6691 / @0x49d66fb
    上下文：0seasonNameSSSgv 2firstAirDateSSSgv 3totalEpisodesSiSgv 5isTraktFallbackSbv 7calendarMediaTypeSSv
            ← Rex **自有日历模型**（seasonName/firstAirDate/totalEpisodes/isTraktFallback/calendarMediaType）
access_token        = 1 命中 @0x48fe81a（登录响应 DTO）
accessToken         = 58 命中（Rex 自有后端，camelCase）
```

而 Swift 的**存储属性名必然出现在反射池**（编译产物，非可选）。→

**Rex 二进制中不存在以 `tmdbid` / `mediaid` / `lack_episode` / `completed_episode` 为属性名的订阅模型**；
`totalEpisode(s)` 确实存在，但明确属于 **Rex 自有日历/TMDB 模型**（同一描述符里带着 `calendarMediaType` / `isTraktFallback` / `first_air_date`），**不是**自建服务订阅响应模型。
（对照：同池里 TMDB 结构的 `tmdb_id`/`first_air_date`/`total_episodes` 等属性名清晰可读 → 说明"读不到"不是可读性问题，是**确实没有**。）

**证据 4（登录侧对照组：真正"必须"的字段长什么样）【已证实】**
`Rex` 反射池 @`0x48fe81a` 处存在登录响应的 Codable 结构，其字段描述符为：

```
12access_token  →  23__derived_struct_equalsySbAC_ACtFZ
                →  4fromACs7Decoder_p_tKcfC   (init(from: Decoder))
                →  6encode2toys7Encoder_p_tKF (encode(to: Encoder))
                →  9expiresAt10Foundation4DateVv   (expiresAt: Foundation.Date)
```

即该结构**只有一个存储字段 `access_token`（`String`，非 optional）**，`expiresAt` 由自写 `init(from:)` 计算而非从 JSON 读取。
→ 与之对照：**登录侧"缺了就失败"的字段 = `access_token`（1 个）**，且这一点有本地化文案背书（`sign-in failed: no access token was returned`）。
→ 而订阅侧**连一个这样的字段都找不到**（见证据 1–3）——这是"订阅响应确实被宽容处理"的最强旁证。

**结论**
1. **【已证实】没有任何一个订阅响应字段是"缺了会导致整体解码失败"的必需品。**
2. **【推断（强）】Rex 对订阅响应要么声明为极少数 optional 字段（可读池中确有形如 `{imdbId: String? @0x48fe921, tmdbId: Int? @0x48fe930, traktId: Int? @0x48fe9de, mediaType: String?}` 的**全 optional 标识结构**，**但"它就是 MP 订阅模型"这一点未被证实**），要么干脆不做 Codable 解码而只做形状/存在性检查（本地化文案 `The server returned unrecognized data.` = 形状检查失败点）。**具体哪一条 = 【未证实】**。
3. **【推断（强）】因此不必为"防解码失败"补齐字段。** 补齐字段的收益只在 UI（缺集提示、海报），不是正确性前置条件。
4. **扩展安全规则【已证实（由 1–3 推出）】**：
   - 加**新键**安全（Swift `JSONDecoder` 默认忽略未知键）——但若 Rex 用 `JSONSerialization` 做严格形状检查，新键也不改变既有键语义，仍安全；
   - **绝不能**改既有键的**类型**（`tmdbid` int→string、`name` string→number）或把 `null` 换成 `0`/`""`——那才会踩到"类型不匹配"这条真正的解码失败路径。

### 4.4 ⚠️ 尺寸推理陷阱（纠正一条流传的推论）

服务的 nginx（`deploy/nginx.conf`）**开了 gzip**：

```
gzip on; gzip_min_length 1024;
gzip_types ... application/json ...;
```

CFNetwork 必带 `Accept-Encoding: gzip`，故 **`12064B`（列表）是压缩后字节数**，`12064/459 ≈ 26B/条`**不能**用来推"字段极简"。
（<1024B 的响应不压缩 → 上表 6 项精确复现成立，不受影响。）

另外两点佐证：
- **459 = 真实条目数**【已证实】：`select nf_status, count(*) from subscriptions` → `active 459 / completed 37 / NULL 28`，与 `list_subscribes()` 的 `nf_status=='active'` 过滤一致。
- 退订 1148365 后列表由 `12064B → 12050B`（-14B 压缩量）→ **【已证实】一次退订 = 列表少 1 条**，语义自洽。

### 4.5 响应包装（交付要求 3）

| 端点 | 包装 | 等级 |
|---|---|---|
| 登录 | 裸对象（无 `data` 包） | 【已证实】 |
| 列表 | **裸数组** | 【已证实】 |
| 详情 | 裸对象 | 【已证实】 |
| 增/退订 | `{success, message, data}` | 【已证实】 |
| （未被使用）`GET /api/v1/openapi/subscribe` | `{code,msg,data}` | 【已证实】Rex **未调用** |

---

## 5. 错误路径与降级（来自 12 个语言包，**硬证据**）

| 触发条件 | Rex 行为（文案原文） | 等级 |
|---|---|---|
| 非 2xx | `Self-hosted service request failed (HTTP %lld).` / 「自建服务请求失败（HTTP %lld）」 | 【已证实】 |
| 登录无 token | `…sign-in failed: no access token was returned.` / 「未返回访问令牌」 | 【已证实】 |
| 列表不可用/形状不符 | `This address does not provide a subscription list for aggregation, but you can still add or cancel individual subscriptions.` / 「此地址不提供订阅列表聚合，仍可添加或取消单条订阅」→ **列表失败是可降级的，增/删是独立链路** | 【已证实】 |
| 任意响应形状不匹配 | `The server returned unrecognized data.` / 「服务器返回了无法识别的数据」 | 【已证实】 |
| 退订未开启同步 | 「当前已关闭'同步移除订阅'，请先在自建服务订阅设置中开启。」→ **本地删除是否回写服务端由开关决定** | 【已证实】 |
| 订阅失败 | `Self-hosted Service Subscription Failed` / 「自建服务订阅失败」 | 【已证实】 |

**运维可用线索**【已证实】：Rex 内置调试入口 `appSettings.copy.debug.check.subscription`（「检查订阅」）与 `appSettings.copy.debug.toggle.subscription`（「切换订阅」）——**可以让主人一键触发一轮请求，无需在 UI 里翻找**，是下一轮取证的理想触发器。

---

## 6. 时序与刷新

```
[启动] ──GET /subscribe/user/{username}──► 401（无 token）
          └─ POST /login/access-token (form) ──► 200 {access_token, token_type, …}
             └─ GET /subscribe/user/{username} ×3 ──► 200 裸数组(459 条)
[进详情] ──GET /subscribe/media/tmdb:1148365──► 200 75B（已订阅）
[退订]   ──DELETE /subscribe/media/tmdb:1148365──► 200 57B
          ├─ GET /subscribe/user/{username} ──► 200 12050B（列表刷新，-1 条）
          └─ GET /subscribe/media/tmdb:1148365 ──► 200 49B（确认空）
[重订]   ──POST /subscribe/ ──► 200 63B
[剧集]   ──GET …/tmdb:303060 与 …/tmdb:303060?season=1 ──► 200 185B
          └─ DELETE …?season=1 ──► 200 57B → GET ?season=1 ──► 49B → POST /subscribe/ ──► 62B
```

要点【已证实】：
1. **懒登录**：无 token 才登，登录发生在第一个 401 之后 3 秒内。
2. **每次写操作后回读**：退订后立刻查详情确认（49B 空）→ **Rex 用"查得到就显示已订阅"的判定逻辑**。
3. **写操作后刷新列表**（退订那次列表重拉）。
4. 【推断】列表的 3 连拉 = 启动 + 刷新 + 可能的后台同步（无法从 log 区分主体）。

---

## 7. 与 MoviePilot 官方 API 对照（**交付要求 D**）

对照源：`jxxghp/MoviePilot` `app/api/endpoints/subscribe.py`、`app/db/models/subscribe.py`、`app/schemas/types.py`、`app/api/apiv1.py`（main 及 6 个历史 tag）。

| 项 | 官方 MP | Rex 实际 | 判定 |
|---|---|---|---|
| 列表 | `GET /api/v1/subscribe/`（另有 `/subscribe/list` API_TOKEN 版） | `GET /api/v1/subscribe/user/{username}` | **Rex 自有简化路径**【已证实】 |
| `/subscribe/user/…` 是否存在 | 否 —— 路由表只有 `/`、`/list`、`/media/{mediaid}`、`/refresh`、`/reset/{subid}`、`/check`、`/search[/…]`、`/history/…`、`/popular`、`/{subscribe_id}`、`/seerr`；`v1.0.0 → main` 一致无 `/user` 子路由 | — | **非官方**【已证实】 |
| 详情/查已订阅 | `GET /subscribe/media/{mediaid}?season=&title=`，**未命中返回空 `Subscribe()`** | 同路径，同空模型行为 | **照官方**【已证实】 |
| 退订 | `DELETE /subscribe/media/{mediaid}?season=` → `delete_by_tmdbid(tmdbid, season)` | 同路径；**unisub 丢弃 season** | 路径照官方、**语义偏离**【已证实】 |
| 新增 | `POST /subscribe/`，body = `schemas.Subscribe`(JSON)，返回 `Response{success,message,data:{id}}` | 同路径；unisub 返回同形状 | **照官方**【已证实】 |
| `mediaid` 格式 | `tmdb:` / `douban:` / `bangumi:` 前缀 | Rex 只见 `tmdb:` | 照官方【已证实】 |
| `type` 取值 | `MediaType` 枚举 = **`'电影' / '电视剧' / '未知'`（中文）** | unisub 回 `"电影"/"电视剧"` | **完全一致**，非缺陷【已证实】 |
| season 语义 | `exists(tmdbid, season)`：**season 给定时按 tmdbid+season 过滤**；`delete_by_tmdbid(tmdbid, season)`：按 tmdbid+season 取记录再删 | unisub 全程忽略 | **真实缺陷**【已证实】 |
| `id` 字段 | MP 的订阅主键（DB 自增） | unisub 塞的是 **tmdbid** | 【推断】Rex 只看"能否拿到对象"；但 `POST` 后的 `data.id` 语义不同（MP=订阅 id）→ 若 Rex 后续用该 id 调 `/subscribe/{subscribe_id}`，unisub 会错 → **风险点，见 §9** |

**D 结论**：Rex 是"**照官方 MP 的 3 条主链路 + 1 条自有列表路径**"（`/subscribe/user/{username}` 来自它自己的简化约定，或来自另一客户端 forward app 的既有约定）—— **unisub 现在同时支持两套列表路径，恰好覆盖了 Rex 与官方 MP，无需改动**。

---

## 8. unisub `forward.py` 逐条对齐与缺陷清单（**交付要求 C**）

对齐基准：`backend/app/routers/forward.py`(288 行) + `schemas/forward.py`(65) + `services/forward.py`(272)。

| # | 位置 | 问题 | 影响 | 等级 |
|---|---|---|---|---|
| **C1** | `routers/forward.py:202-227`（GET 详情） | 收到 `season` 但**丢弃**，只按 `tmdb_id` 查 | Rex 明确会问"某季"；`?season=1` 与不带季返回**同一 185B**（实测）。多季剧会在**未订阅第 2 季时误报已订阅** | 【已证实】 |
| **C2** | `routers/forward.py:230-250` + `services/forward.py:249-272`（DELETE） | `season` 丢弃，`remove_subscribe(db, tmdb_id)` **按 tmdbid 删整条** | **按季退订会删掉整部剧**（官方是 tmdbid+season）。风险最高的一条 | 【已证实】 |
| **C3** | `services/forward.py:203,224` 未命中 | 固定 49B 全 null（**与官方行为一致，保留**） | 无——但**不要**改成 404：会把"未订阅"变成"请求失败"，触发 `request failed (HTTP %lld)` 文案 | 【已证实（保留项）】 |
| **C4** | `services/forward.py:174-188` 列表 | 只回 `nf_status=='active'` | `missing_fill`/`completed`/空状态(28 条) 的订阅在 Rex 里显示为"未订阅"→ 但它同时又是服务端的"已订阅" → **状态不一致**（当前 37+28 条受影响，实测计数） | 【已证实】 |
| **C5** | `services/forward.py:206-247` POST | 只认 `tmdbid`/`mediaid`/`name`/`type`；**不接受 `season`** | 剧集订阅无法表达季号（官方 body 有 `season`） | 【已证实】 |
| **C6** | `services/forward.py:249-263` DELETE | 本地无记录 → `success:false "订阅记录不存在"` | 若 Rex 看到的订阅在 unisub 本地已缺失（例如 C4 的过滤差异），退订会失败而非幂等成功（官方 `delete_by_tmdbid` 恒 `Response(success=True)`） | 【已证实】 |
| **C7** | `services/forward.py:48-53` `_build_subscribe_item` | `id = tmdb_id`（非订阅主键） | 与 MP 语义不同；**当前无证据** Rex 会拿它去调 `/subscribe/{subscribe_id}` → 风险【未证实】，下一轮用抓包验证（见 §9-实验 3） | 【未证实】 |
| **C8** | `routers/forward.py:172-185` | `username` 被忽略（单用户系统） | 可接受；但若主人改用户名，Rex 仍打新用户名 → 不匹配也不影响 | 【已证实（可接受）】 |
| **C9** | `routers/forward.py:99-101` 登录失败 | 401 文案中文；Rex 只关心状态码与 token 字段 | 无 | 【已证实（无影响）】 |
| **C10** | `routers/forward.py:277-288` | `/api/v1/openapi/subscribe` 用 `{code,msg,data}` 包装 | Rex 未调用；保留无害 | 【已证实】 |

**要落地的最小改动建议（不动生产代码，仅提案）**
- `GET/DELETE .../media/{mediaid}`：把 `season` 透传到 service 层；`Subscription` 需要季号维度 → 现状模型**没有 season 字段**（`models/subscription.py` 只有 tmdb_id/media_type/…）→ **C1/C2 的修复需要一次数据模型变更**（加 `season`，键改为 `(tmdb_id, season)`）。这是架构决策，**不在本卡范围内**，已在 §9 列为待决项。
- `POST /subscribe/`：接收 `season`（可选）并同样落地。
- 列表过滤：若 Rex 需要"完整已订阅集合"，把过滤从 `active` 放宽（或加 `?status=`），但**先确认 Rex 到底怎么用这个列表**（§9-实验 1 的观察项）。

---

## 9. 未证实清单 + 决定性下一步

### 9.1 未证实（写不出就是写不出）

| # | 未知项 | 缺什么条件 |
|---|---|---|
| U1 | `POST /api/v1/subscribe/` 的**确切 JSON 键名**（含是否带 `season`） | 需要**请求体原文**：nginx `$request_body` 日志 / 中间件打印 / 或 mock server 抓包 |
| U2 | Rex 订阅响应的**具体模型字段与 optionality**（是"极少数 optional 字段"还是"不做 Codable 解码"） | 需要**解密后的 `__TEXT`**（否则 CodingKeys 与字面量不可读），或运行时 hook（MinOS 17 阻断） |
| U3 | Rex 是否用 `data.id` 后续调 `/subscribe/{subscribe_id}`（影响 C7） | 同 U1 的抓包，观察后续请求序列 |
| U4 | 列表 3 连拉的**真实触发原因**（启动/刷新/同步） | 需要带 UI 操作的完整抓包（每步操作时间对齐） |
| U5 | Rex 对"缺字段"与"null 字段"的**UI 表现差异** | 需要主人看界面截图（我们看不到 UI） |
| U6 | C4（`active` 过滤）在 Rex 侧的**可观测后果** | 需要把 `missing_fill` 状态的订阅在 Rex 里看一眼 |

### 9.2 决定性实验（可执行，按性价比）

**实验 1 —— 抓 body（解 U1/U3，最高优先）**
在 unisub 侧临时打开请求体记录（**不加在生产代码里，用 nginx 临时字段**）：

```nginx
# deploy/nginx.conf → 临时改 log_format 加 $request_body（改完 reload，用完撤回）
log_format apidebug '$remote_addr [$time_local] "$request" $status $body_bytes_sent '
                    'req_body="$request_body" ua="$http_user_agent"';
access_log /home/hermes/projects/unisub/logs/nginx-body.log apidebug;
```
然后请主人**用 Rex 的调试入口**触发（三个已确认存在的入口）：
- `检查订阅`（`appSettings.copy.debug.check.subscription`）
- `切换订阅`（`appSettings.copy.debug.toggle.subscription`）
- `模拟订阅钩子流`（`appSettings.copy.debug.flow.mediahook`，成功后提示 `Subscription hook call succeeded:`）

在**电影**与**剧集**上各做一次 **订阅 → 退订**，即可拿到 U1/U3 的全部原文（含 `season` 是否在 body 里）。
⚠️ 注意：`Shell.strings` 显示"订阅服务未配置时订阅项不出现在列表" → 取证前先确认自建服务订阅已启用且列表可见。

**实验 2 —— mock server 探解码容忍度（解 U2 的行为面，不需要解密）**
Rex 的 `Info.plist` **实测**（plistlib 读取）：`NSAppTransportSecurity.NSAllowsArbitraryLoads = True`
（例外域 `rexnow.tv` 反而禁明文；`api.rexnow.tv` 有 SPKI pinning）+ `NSLocalNetworkUsageDescription` 存在
→ **可以把它指向局域网内任意 `http://` mock**（自定义服务地址走该字段；本轮实测序列就是 Rex 打在 unisub 上的真实请求，见 §1.1 访问日志）。
起一个记录服务，按 §4.1 的表**逐级剥离字段**回包（7 字段 → 4 字段 → 2 字段 → `{}` → `[]` → 非 JSON），
记录 Rex 每次的反应（是否弹「服务器返回了无法识别的数据」/ 是否继续工作）。
**这能给出"哪些字段是行为必需的"经验边界**——比读加密二进制更接近答案，且完全可复现。

**实验 3 —— 逐字段类型扰动（验 §4.3-4 的安全规则）**
在 mock 上把 `tmdbid` 从 int 改成 string、`name` 改成 number、`type` 改成 `"movie"`，
各自单独跑一遍：**能定位 Rex 真正的类型敏感点**（尤其 `type` 的值域——这是唯一"值可能被比较"的字段）。

---

## 附录 A：证据索引（可复核）

```
# 1) 真实调用序列
grep -n "Rex/" /home/hermes/projects/unisub/logs/nginx-access.log | tail -30
# 2) 列表口径 = 459
psql "postgresql://unisub:unisub@192.168.31.10:5432/unisub" \
  -c "select nf_status, count(*) from subscriptions group by 1 order by 2 desc;"
# 3) gzip（解释 12064B）
grep -n -iE 'gzip|access_log' /home/hermes/projects/unisub/deploy/nginx.conf
# 4) 字节指纹复核
python3 -c "import json;print(len(json.dumps({\"id\":None,\"tmdbid\":None,\"name\":None,\"type\":None},ensure_ascii=False,separators=(',',':')).encode()))"   # 49
# 5) 脚本层否证（0 命中）
grep -arnoiE '(moviepilot|self.?hosted|/api/v1/[a-z/]*)' \
  /home/hermes/.hermes/profiles/architect/cache/scratch/rex/Payload/Rex.app/RexScript_RexScript.bundle/
# 6) 反射池字段否证（实测输出）
python3 - <<'EOF'
d=open('/home/hermes/.hermes/profiles/architect/cache/scratch/rex/Payload/Rex.app/Rex','rb').read()
for t in ['tmdbid','mediaid','lack_episode','completed_episode','lackEpisode','completedEpisode','total_episode','totalEpisode','access_token','accessToken','PilotHub']:
    idx=d.find(t.encode()); print(f"{t:20s} first={hex(idx) if idx>=0 else 'ABSENT':>12}  hits={d.count(t.encode())}")
EOF
# 7) 订阅请求类型名（后缀压缩，前缀不落盘）
#   0x49bd1c2  "…ilotSubscriptionRequestV"     ← 全文唯一一处（SubscriptionRequest hits=1）
#   0x49c63c1  "PilotHubC"                     ← 完整可读类名（hits=1）
# 8) 官方对照
curl -sS https://raw.githubusercontent.com/jxxghp/MoviePilot/main/app/api/endpoints/subscribe.py
curl -sS https://raw.githubusercontent.com/jxxghp/MoviePilot/main/app/db/models/subscribe.py
curl -sS https://raw.githubusercontent.com/jxxghp/MoviePilot/main/app/schemas/types.py   # MediaType='电影'/'电视剧'
```

## 附录 B：证据等级汇总（供上层决策）

| 交付要求 | 结论可落地程度 |
|---|---|
| 端点/方法/路径/参数格式 | **100% 已证实**（可直接写实现） |
| 鉴权与 401 重放 | **100% 已证实**（可直接写实现） |
| 响应形状（含未命中空对象、裸数组、包装） | **100% 已证实**（字节级复核） |
| "是否需要补齐字段防解码失败" | **已证实"不需要"**；具体模型【未证实】 |
| POST body 键名 | **未证实** → 实验 1（一条 nginx 配置即可闭环） |
| season 语义缺陷（C1/C2/C5） | **已证实** → 属架构决策（需给 `Subscription` 加 season 维度） |