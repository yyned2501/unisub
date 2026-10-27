"""NextFind 双向同步的各阶段实现。

从 nf_sync.py 拆出的阶段函数集合，按方向分包：
    - common: 各阶段共用的状态判定工具
    - nf_to_local: Phase 0 / 1 / 1.5（NF 状态清理与回写本地）
    - local_to_nf: Phase 2（推送本地订阅到 NF）
    - completion: Phase 3 / 4 / 5（完成判定与日志）

每个阶段函数均为模块级函数（无共享状态），由 NfSyncEngine 按顺序编排调用。
"""

from __future__ import annotations

from app.services.nf_sync.phases.completion import (
    phase3_movie_completed,
    phase4_tv_completed,
    phase5_log_cancelled,
)
from app.services.nf_sync.phases.local_to_nf import phase2_local_to_nf
from app.services.nf_sync.phases.nf_to_local import (
    phase0_clean_abnormal,
    phase1_5_blacklist,
    phase1_nf_to_local,
)

__all__ = [
    "phase0_clean_abnormal",
    "phase1_5_blacklist",
    "phase1_nf_to_local",
    "phase2_local_to_nf",
    "phase3_movie_completed",
    "phase4_tv_completed",
    "phase5_log_cancelled",
]
