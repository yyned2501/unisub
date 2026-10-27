# SPEC：全项目解耦 + 重复/近似功能收敛（Phase D）

- 作者：architect ｜ 日期：2026-10-01 ｜ 状态：D1 审计卡已建（只读），D2 动刀卡待 architect 评审后开
- 仓库：`/home/hermes/projects/unisub`（整体：`backend/app`、`backend/scripts`、`frontend/`）
- 前置：Phase 4B（JEV 落地）完成 → 避免审计基线被并发改动污染

## 0. 现状证据（实测，2026-10-01）

> ⚠️ **2026-10-01 更正——本节 4 处与审计实测不符，以 `docs/decoupling-audit.md` §2 为准**：
> ① 「上游客户端 4 个（同一模式）」→ 实为 **3 个** HTTP 客户端（`clouddrive2.py` 是 gRPC 门面，不走 header 鉴权）；
> ② 「跨文件名同名函数 14 组」→ 实测 **28 组 / 46 def**；
> ③ 「`emby.py` 文件内 `sync_cache` ×2（同一职责）」→ **不成立**：`services/emby.py:250`(3 行薄委托) vs `routers/emby.py:49`(端点) 是正常分层，**判误判、禁止合并**；
> ④ 「services 33 文件」→ **32 + `__init__.py`**。
> 另：**分层逆向依赖改前即 0 条**（§2 目标已达成，不作为收益）。排批以审计 §7 为准，R1/R2 判定与白名单以审计 §5 为准。

- 仓库 tracked 249 文件；`backend/app` **102 个 .py**，合计 ≈23.3k 行
  → 其中 `core/clouddrive_pb2_grpc.py` **10,735 行** + `core/clouddrive_pb2.py` 669 行是**生成代码**，
  真实手写代码 ≈**11.9k 行**。**行数密度说明问题不在"代码多"，在模块簇重叠。**
- `services/` 33 个文件，模块簇：
  - **Emby 家族 5 个**：`emby.py`(279) / `emby_db.py`(271) / `emby_cache_sync.py`(296) / `emby_scan.py`(196) / `emby_tmdb_update.py`
  - **TMDB 家族 4 个**：`tmdb.py`(192) / `tmdb_cache.py`(213) / `tmdb_detail.py` / `tmdb_cache_migration.py`
  - **上游客户端 4 个**：`nextfind.py`(215) / `moviepilot.py`(308) / `clouddrive2.py` / `clouddrive_client.py`(188)（同一模式：构造 `base_url`+`api_key` → `_headers` → 超时 → 错误映射）
  - **同步引擎**：`nf_sync.py` + `nf_sync_phases/{nf_to_local,local_to_nf}.py`(256) / `mp_sync.py`(285) / `mp_missing.py`
  - **配置读写 3 套**：`ai_config.py` / `auto_subscribe/config_store.py`(209) / `platform.py`
  - **订阅路径 4 层**：`routers/subscriptions.py` + `routers/forward.py`(288) + `services/forward.py`(272) + `services/subscription.py`(193) + `services/orchestrator.py`(407)
- 同名函数跨文件统计（ast 扫描，非 `__init__`）：`create_subscription` ×4、`save_config` ×4、`test_connection` ×4、`fetch_async` ×4、`load_config` ×3、`clear_history` ×3、`mask_api_key` ×2、`sync` ×2、`subscribe` ×2、`unsubscribe` ×2、`search` ×2、`get_seasons_map` ×2、`update_cache_for_tv` ×2、`get_season_completion` ×2（后三者在 `tmdb.py` 是 3 行、`tmdb_cache.py` 是 18~55 行 → 疑似薄包装转发）
- **文件内重复**（同一文件内同名多次实现）：`emby.py` 的 `sync_cache` ×2（3 行 / 12 行）
- 未跟踪脚本堆：`backend/scripts/`（探针/一次性脚本，未纳入 git）

## 1. 什么是"重复/近似功能"（判定标准，必须按类别写清单）

| 类别 | 定义 | 处置方向 |
|---|---|---|
| **R1 真重复** | 同一语义算法/映射在某处被逐字或近似拷贝（例：`emby.py` 内 `sync_cache` ×2 是**同一职责**的两次实现） | **合并**：留单点实现，删副本 |
| **R2 近似重复** | 同一领域封装了多套（Emby/TMDB 家族、4 个上游客户端的鉴权+超时+错误模板、3 套配置读写） | **抽象**：抽公共基座 + 保留各源差异化配置 |
| **R3 有意重复** | 接口相同、实现必须不同的适配器：`auto_subscribe/{douban,maoyan,mikan,bangumi}.py` 的 `fetch_async`；DTO 同名字段 | **保留**，只统一签名 |
| **R4 生成/第三方代码** | `core/clouddrive_pb2*.py` | **不动** |
| **误判（禁止合并）** | **同名但不同职责**：`NextFindClient.create_subscription` / `MoviePilotClient.create_subscription` / `OrchestratorService.subscribe` —— 这是分层的正常体现，合并即破坏边界 | **保留**，写明理由 |

**硬约束：R1/R2 的每一条清单项都必须给出「依据」**（相同点、差异点、谁在调用、合并后差异如何配置化）。给不出依据 → 归 R3 保留。

## 2. 解耦原则（依赖方向，可量化）

- 目标分层：`routers/` → `services/` → `core/`；`models/`、`schemas/` 是可被上层依赖的叶子。
- 禁止项：`services/` 不得 import `routers/`；`core/` 不得 import `services/`；`auto_subscribe/pipeline/` 不得 import `routers/`（pipeline 是纯算法，只依赖 clients 与 models）。
- **量化判据**：用 ast 生成 import 图，统计"逆向依赖"条数 → **目标 0**，报告里给出改前/改后数字。
- 禁止为了解耦引入新中间层（DI 容器、抽象工厂）——只在**有 ≥2 个真实使用方**时才抽公共模块。

## 3. 处置分级（每一条清单项必须落到其一）

1. **合并**：删副本，指向单一实现（必须附"被删代码 ↔ 等价新位置"对照）。
2. **抽象**：抽公共模块，差异走参数/配置（必须附差异清单 + 迁移映射）。
3. **保留**：写进白名单，附理由（R3/R4/误判）。

**禁止**：为"看起来统一"做大抽象；为了减少行数牺牲可读性；顺手改行为或对外契约。

## 4. 量级约束

- **单批 ≤ 8 个文件、净变化 ≤ 400 行**；每批一个 commit、可独立回滚。
- 每批必须保持**行为不变**：`pytest` 全绿 + **OpenAPI 快照 diff 为空**（`routers/` 路径与字段不得变化）。
- 冒烟四件事每批跑一次：订阅一部 / 取消一部 / 扫描一次 / 触发一次同步。
- D1 清单要能排出批次顺序，规则：**先删死代码与 R1 → 再抽 R2 上游客户端/配置 → 最后 Emby/TMDB 家族**（风险从低到高）。

## 5. 非目标

- 不做全仓重写、不换框架、不引入 DI/抽象工厂。
- 不动生成代码、`migrations/`、测试夹具。
- 不改对外 API 契约（路径/字段/状态码），不改前端视觉与构建链。
- **不与 Phase 3（S8 死代码清理）重叠**：Phase3 只删"零引用文件"；「重复功能合并」归本 spec。两卡同时 ready 时先跑 Phase3。
- 不做性能优化（那是 Phase 1/2 的范围）。
- **前端 `onImgError` 双实现（审计 §5.5 R1-F1）：本期不改视觉**（architect 2026-10-01 裁决）。
  理由：合并必然改变其中一侧的表现（隐藏 vs 占位图），属新增视觉决策、超出本 spec 非目标 → 转白名单；
  批次 4 只做文档漂移修正（`AGENTS.md` 结构表与 `utils/common.ts`）。要统一视觉另开卡，需先定基线 + 人工确认列表页。

## 6. 两阶段（D1 只读审计 → 评审 → D2 动刀）

- **D1（本卡）**：只读。产出 `docs/decoupling-audit.md`：
  - 逐条清单项：`file:line` + 类别（R1/R2/R3/保留）+ 依据（相同/差异/调用方）+ 建议处置 + 影响面 + 风险 + 预估收益 + 建议批次
  - import 图逆向依赖清单（改前条数）
  - 零引用文件清单（交 Phase3 执行，不自己删）
  - **禁止改任何代码**（含"顺手删一行"）
- **D2（architect 评审 D1 后开卡）**：按批次动刀，每批按 §4 验收。

## 7. 验收命令

```bash
# D1（审计）
test -f docs/decoupling-audit.md && wc -l docs/decoupling-audit.md
git status --short backend/app frontend   # 期望：空（审计不得改代码）

# D2（每批）
cd /home/hermes/projects/unisub/backend && unset UNISUB_DATABASE_URL && .venv/bin/python -m pytest -q   # 全绿
# OpenAPI 快照 diff（改前保存，改后对比）
.venv/bin/python -c "import json,os;os.environ.setdefault('REQUIRE_AUTH','1');from app.main import app;open('/tmp/openapi_after.json','w').write(json.dumps(app.openapi(),sort_keys=True,ensure_ascii=False,indent=1))"
diff /tmp/openapi_before.json /tmp/openapi_after.json && echo "契约未变 ✓"
# 分层违规计数（改后应为 0）
```
