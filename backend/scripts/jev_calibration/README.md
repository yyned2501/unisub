# JEV 阈值标定资产（4A 产物固化）

> 上游：`docs/SPEC-JEV-DECISION.md` §9（2026-10-02 architect 复算）、`docs/jev-replay-report.md`（Phase 4A）
> 用途：给 `scripts/jev_replay_resweep.py` 提供输入，**同一批 state 零 API 成本重算阈值曲线**。
> 原先只存在于 `/tmp/jev_replay`，重启即丢；本目录为其仓库固化版本。

## 文件

| 文件 | 内容 | 行/条数 |
|---|---|---|
| `samples.json` | 712 条真实历史样本：源标题/年份/类型、候选池、A 侧决策（`a_accept`/`a_pick_id`）、标签 `truth_ids`、`veto_state_hash` | 712 条（854 KB） |
| `items_veto.jsonl` | 515 条闸门 state（A 侧兜底候选，送 JEV 的输入） | 515 行 |
| `items_veto_manifest.json` | state 哈希序，用于对齐 `out_*.jsonl` 的行序 | 515 条 |
| `questions_veto_soft.json` | **旧**（v2）指令副本 —— 生产改造前的形态 | — |
| `questions_v3.json` | **现行**（v3）指令权威副本 —— 与 `app/services/decision_payload.py:SAME_WORK_INSTRUCTION` 必须逐字一致 | — |
| `out_veto_soft.jsonl` | v2 指令逐例输出（`same_work__0.noul` 等） | 515 行 |
| `out_veto_v3.jsonl` | v3 指令逐例输出 | 515 行 |
| `metrics.json` | 4A 评价脚本原始指标（成本/token/延迟/混淆矩阵） | — |
| `eval_out.txt` | 4A 评价脚本控制台原始输出 | — |

## 复跑

```bash
cd backend && .venv/bin/python scripts/jev_replay_resweep.py     # 只读，不写任何文件
```

`τ=0.75 + v3` 的验收结论（2026-10-02 复算，脚本实测输出）：

- 真实漏订（A 已采纳却被拦）：τ=0.5+v2 = **5** → τ=0.75+v3 = **0**
- 闸门误放行：τ=0.5+v2 = 2 → τ=0.75+v3 = 6（标签口径误标，人工判读全部为同作品）
- 同名却被拦：v3+0.75 仅 1 条（`爸爸`，A 侧未采纳、根本不进闸门）；τ=0.80 下多 1 条 OOD（`逃亡者`，生产走精确匹配）

## 注意

- 这两个 jsonl 里 `questions` **只问 `same_work__0`**；`which__0` 只是 JEV 对旧指令的附带回答，闸门不读（红线）。
- 本目录是**只读标定资产**，不要在运行时被服务引用；改指令只改 `app/services/decision_payload.py` 并同步 `questions_v3.json`。
- `samples.json` 含真实订阅历史（标题/年份/TMDB id），无密钥。
