# SPEC：自动订阅识别召回修复（"未匹配"归因与召回）

- 作者：architect ｜ 日期：2026-10-10 ｜ 状态：**待实现（coder）**
- 关联：`docs/SPEC-JEV-DECISION.md`（兜底闸门）、`app/services/auto_subscribe/pipeline/{resolve,matching,search}.py`
- 触发：主人报"自动订阅最近有很多未匹配"

## 0. 事实基线（实测，非推断）

`app/data/auto_subscribe_history.json`：handled **844** 条 → `exists 292 / subscribed 345 / unrecognized 35 / filtered 172`。
最近一轮（2026-10-10 00:09）**8 条未识别**（mikan 7 + douban 1），全部走 AI 兜底、全部无声返回。
离线复现（真实调 TMDB/NF/LLM，探针见 §7）把每条钉到代码行：

| 条目 | 全名搜索 | 已生成的基础变体 | 真实命中 | 现状 |
|---|---|---|---|---|
| 弹珠汽水瓶里的千岁同学 第2部分 | 10 条垃圾 | `弹珠汽水瓶里的千岁同学` → **1 条精确命中 (2025,tv)** | ✅ 有 | 选中 `乱马½` → 相似度不过 → 未识别 |
| 魔法姐妹露露特莉莉 第2部分 | 10 条垃圾 | `魔法姐妹露露特莉莉` → **`魔法姐妹露露和莉莉(2026,tv)`** | ✅ 有 | 同上（选中 `乱马½`） |
| 怪兽8号 鸣海的平日 | 10 条垃圾 | **无此变体**；补 `怪兽8号` → **`怪兽8号(2024,tv)`** | ✅ 有 | 选中 `Stranger Things…` → 不过 |
| 桃源暗鬼 ～日光・华严之泷篇～ | 0 条 | **无此变体**；补 `桃源暗鬼` → **`桃源暗鬼(2025,tv)`** | ✅ 有 | 无候选 |
| 东京复仇者 三天战争篇 | 0 条 | **无此变体**；补 `东京复仇者` → tv 侧 `重生之道(2021,tv)`（动画本体的另一译名） | ⚠️ 译名 | 无候选 |
| 杀手旅店 第二季 | 变体已剥离 | `杀手旅店` → `异人旅馆(2025,tv)` | ⚠️ 译名待确认 | 相似度不过 |
| 巴黎绽放的星辰 | 0 条 | — | ❌ TMDB 无 | 真·查不到 |
| 神秘面包小子 | 0 条 | — | ❌ TMDB 无 | 真·查不到 |

## 1. 根因（R1~R6，每条都有证据）

- **R1 变体搜索"第一个非空即返回"**：`_search_with_variants` 一旦某变体返回任何结果就 `return`。
  全名搜索被 TMDB 模糊匹配成 10 条垃圾（`坠落2：死点`、`宝莱坞鸡尾酒2`…），于是**永远轮不到已经生成的基础变体**，
  而正确候选恰恰在那一步。→ 有正确候选仍判"未识别"。
- **R2 无候选池、相似度不过即整条放弃**：`pick_best_gated` 只在**单一结果集**里选；选出的垃圾被 `title_similar_enough` 否决后
  直接 `return None`，不做候选级/变体级重试。
- **R3 变体规则覆盖不足**：无"空格/`·`/`-` 分隔的副标题"剥离、无 `～…～` 包裹段剥离 →
  `怪兽8号 鸣海的平日`、`东京复仇者 三天战争篇`、`桃源暗鬼 ～…～` 只搜全名。
- **R4 mikan 详情解析正则过时（源侧）**：站点已把 `bangumi.tv/subject/NNNN` 改为 **`bgm.tv/subject/NNNN`**
  （实测代理取页 `https://bgm.tv/subject/499474`），而 `BGM_ID_RE = r"bangumi\.tv/subject/(\d+)"` →
  **73 部新番 `bangumi_id` 全空、`year` 全空** → Bangumi 别名兜底 + 年份消歧整条死。
  另：`mikanani.me` 本机**直连不通**（HTTP 000 / 12s 超时 ×3），走代理 200 / 1.0s ×3；镜像 `mikanime.tv` 直连 200 且同样含 `bgm.tv` 链接 → 域名顺序/代理需一并修。
- **R5 AI 兜底静默失效**：`ai_model = deepseek-flash` 是推理模型，**把 token 全烧在 reasoning 上**：
  实测 max_tokens=300 → content 0 字 / reasoning 924 字；max_tokens=2000 → content 0 字 / reasoning 6362 字（跑飞）。
  `_call_llm` 只读 `message.content`，空则 `return None` 且**无任何日志**（日志里 `AI 调用失败`=0、`AI 返回格式异常`=0）。
- **R6 未识别无归因**：history 只存 `status/title/source/time`，没有"为什么"，主人只能看到数字。

## 2. 改动设计

### S1 候选池化 + 精确优先（零成本，修 R1/R2 主因）

- `_search_with_variants` 改为**收集所有变体的结果**（按变体优先级保序、按 `id` 去重），返回候选池；不再"第一个非空即返回"。
- `resolve_best_match` 流程改为：
  1. 对候选池跑 `pick_best_exact`（阶段 1~3，零成本零延迟）→ 命中即返回；
  2. 全不中时，**先用相似度把垃圾候选挡在池外**（`title_similar_enough(原标题, 候选标题)` 不过的候选不进池），
     再对剩余候选跑 `pick_best_gated`（阶段 4/5 + JEV 闸门）；
  3. 仍不中 → `None`（unrecognized，带 reason）。
- **关键**：相似度校验从"事后否决"改成"进池门槛" —— 垃圾候选（`乱马½`、`Stranger Things`）不该进池，
  也就不可能掩盖后面的精确命中。
- **JEV 与相似度的顺序（新增裁决）**：当 JEV 对某候选判 `PASS`（同一部作品）时，**不得再被字面相似度否决**；
  两者都不过才放弃。理由：JEV 就是为"译名/写法差异但同作品"设计的，字面相似度无权推翻它。

### S2 补变体规则（修 R3）

在 `build_search_queries` 追加（**放最低优先级**，仅前面全不中时使用）：
1. 空格/全角空格/`·`/`-` 分隔 → 取首段（`怪兽8号 鸣海的平日`→`怪兽8号`；`东京复仇者 三天战争篇`→`东京复仇者`）；
2. `～…～` / `~…~` / `「…」` 包裹段 → 剥离（`桃源暗鬼 ～日光・华严之泷篇～`→`桃源暗鬼`）。
- 已有规则（第X季/第X章篇话部分/`。`/`：`/剧场版/数字尾）保持不变。
- 判据：新规则必须**实测能命中**才算加（回归集见 §3）。

### S3 修 mikan 详情解析（修 R4，源侧）

- `BGM_ID_RE` 兼容 `bgm.tv`（`r"(?:bangumi|bgm)\.tv/subject/(\d+)"`）。
- 年份提取按**当前页面结构**修（`bangumi-info` 元素已不是 `<p>`：实测页面为 `bangumi-info">放送开始：10/2/2026`）。
- 域名策略：优先可达域名（实测 `mikanime.tv` 直连 200），`mikanani.me` 需代理（本机直连不通）。
- 验收：跑一次 mikan 抓取，73 条里 `bangumi_id` 非空 ≥90%、`year` 非空 ≥90%（现在 **0/73**）。
- **Bangumi 别名（日文原名）必须进变体链**：`_bangumi_assisted_search` 现在拿不到 subject（无 id），修好后
  `東京リベンジャーズ` 这类原名能直接命中 TMDB → 解决 R2 里的"译名不同"类。

### S4 AI 兜底修好且可见（修 R5）

- **模型换 `glm-5.3-flash`**（实测同一 prompt：**3/3 content 非空**、平均 2.9s、识别内容正确；
  对比 `deepseek-flash` 0/2 空、`qwen3.8-flash` 1/3、`gpt-3.5-turbo` 3/3 但年份/季数错、`glm-5.3` 3/3 但把剧判成电影）。
  换模型 = 改 `ai_config.ai_model`（免重启生效）。
- **失败必须落 WARN 日志**：空 content / JSON 解析失败 / 回搜无结果，三种都要带标题落日志（现在全静默）。
- content 为空时，尝试从 `reasoning_content` 里提取 JSON 再兜一次。
- 记录每次调用的模型/延迟/是否空返回，便于成本与质量核算。

### S5 未识别归因（修 R6）

- `unrecognized` 条目在 history 里落 `reason`（`no_candidates` / `similarity_reject` / `gate_reject` / `ai_empty`）
  + `variant`（用了哪个搜索词）+ `top_candidates`（前 3 个候选标题）。
- 前端/接口把 reason 展示出来（"未识别"要能点开看为什么）。

## 3. 验收（回归集必须真跑）

**A. 8 条回归集（本轮真实失败样本，逐条给结论）**

| 条目 | 期望 |
|---|---|
| 弹珠汽水瓶里的千岁同学 第2部分 | 命中 `弹珠汽水瓶里的千岁同学(2025,tv)` → 已订阅/已存在 |
| 魔法姐妹露露特莉莉 第2部分 | 命中 `魔法姐妹露露和莉莉(2026,tv)` |
| 怪兽8号 鸣海的平日 | 命中 `怪兽8号(2024,tv)` |
| 桃源暗鬼 ～日光・华严之泷篇～ | 命中 `桃源暗鬼(2025,tv)` |
| 东京复仇者 三天战争篇 | 经 Bangumi 原名/别名 或 JEV 判同作品 → 命中 `重生之道/东京复仇者(2021,tv)` |
| 杀手旅店 第二季 | 经别名/JEV → 命中 `异人旅馆(2025,tv)` |
| 巴黎绽放的星辰 | 仍未识别，但 `reason=no_candidates`（可归因） |
| 神秘面包小子 | 同上 |

**硬指标：前 4 条必须转正**（0→4），后 2 条要么转正要么必须留下 JEV 判定记录；最后 2 条必须带 `reason`。
**不许把"未识别"改成静默丢弃** —— 宁可留着并归因，也不许伪造命中。

**B. 全量回归**：`cd backend && unset UNISUB_DATABASE_URL && .venv/bin/python -m pytest -q` 全绿（基线 **209**），
新增测试至少覆盖：① 全名出垃圾、基础变体有精确命中 → 必须选精确命中；② 相似度不过的候选不进池；
③ 变体全不中 → `reason` 正确；④ AI 空返回 → WARN 日志 + `ai_empty`。

**C. 线上实证**：改完跑一轮真实自动订阅（手动触发即可），给出前后对照：
`unrecognized` 从 8 条降到 ≤4 条（含 2 条真·无），且新增订阅在库里能查到行。

## 4. 非目标

- 不改精确匹配（阶段 1~3）的语义与阈值；不改 JEV 闸门形态（**仍不许读 `which` 字段**）。
- 不新增搜索源、不改订阅写入/上游推送路径（S-B5 那条线不动）。
- 不为"真·查不到的条目"造数据：TMDB 没有就是没有，只要求可归因。
- 不做全量历史重跑（35 条历史未识别只作为回归集，不批量改库）。

## 5. 红线

- 不许把相似度校验直接删掉（那是误订防线）；只允许"前置为进池门槛"。
- 不许用提高 max_tokens 掩盖 R5（实测 2000 也空，根因是模型跑飞）→ 必须换模型。
- 不许打印任何 key/token；mikan 详情页请求走 `core/http_client`（项目铁律）。
- 改动不得引入裸 urllib/httpx 直连（见 `backend/app/STANDARDS.md`）。

## 6. 交付

- commit（不 push）+ 卡内回帖：S1~S5 各自 diff 位置、回归集 8 条的实际结论（逐条）、pytest 输出、线上前后对照。
- 拆卡建议：S1+S2+S5 一张卡（识别逻辑，本卡）；S3（mikan 源侧）与 S4（AI 模型+日志）如改动面大可拆子卡。

## 7. 复现资产（architect 探针，只读）

- `~/.hermes/profiles/architect/cache/scratch/replay_unrecognized_probe.py`：逐条打印变体/搜索结果/选中项/相似度/AI 原始返回。
- `~/.hermes/profiles/architect/cache/scratch/probe2_variant_and_model.py`：验证补变体能否救回 + AI 模型选型。
- `~/.hermes/profiles/architect/cache/scratch/probe3_mikan_bangumi.py`：mikan 条目字段 + Bangumi 别名。
- 运行：`cd backend && set -a; source .env; set +a; PYTHONPATH=$PWD .venv/bin/python <探针>`
