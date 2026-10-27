"""Schema 漂移校验 — 比对 SQLAlchemy 模型与真实数据库的列差异。

用途：在缺少迁移机制的项目里，模型与生产库会悄悄分叉（模型加了列不落库、
库里手工加了列模型不认）。本脚本把差异显式打出来，可接入 CI/lint 门禁。

用法:
    cd backend && set -a && source .env && set +a && \\
        uv run python scripts/schema_drift_check.py

退出码: 0 = 无漂移, 1 = 存在漂移
"""

import asyncio
import os
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.models  # noqa: F401,E402  触发所有模型注册到 Base.metadata
from app.core.database import Base  # noqa: E402

TABLE_SQL = "select table_name, column_name from information_schema.columns where table_schema='public'"


def _dsn() -> str:
    """把 SQLAlchemy 的 asyncpg DSN 转成 asyncpg 直连 DSN。"""
    url = os.environ.get("UNISUB_DATABASE_URL", "")
    return url.replace("postgresql+asyncpg://", "postgresql://")


def diff(db_columns: dict[str, set[str]]) -> list[str]:
    """比对模型与库的列集合，返回人类可读的漂移描述列表。"""
    problems: list[str] = []
    model_tables = {t.name: {c.name for c in t.columns} for t in Base.metadata.sorted_tables}

    for name, cols in model_tables.items():
        if name not in db_columns:
            problems.append(f"模型有表 {name} 但库里没有（create_all 只建表不改表，换机部署会漏）")
            continue
        missing = cols - db_columns[name]
        extra = db_columns[name] - cols
        if missing:
            problems.append(f"{name}: 库里缺列 {sorted(missing)} → 写操作会失败，需 ALTER TABLE")
        if extra:
            problems.append(f"{name}: 模型未声明多列 {sorted(extra)} → 模型映射不完整或列已废弃")

    for name in db_columns:
        if name not in model_tables:
            problems.append(f"库里有表 {name} 但模型没有 → 无人维护的孤儿表")
    return problems


async def main() -> int:
    """连库比对并输出结果。"""
    conn = await asyncpg.connect(_dsn())
    try:
        rows = await conn.fetch(TABLE_SQL)
    finally:
        await conn.close()

    db_columns: dict[str, set[str]] = {}
    for row in rows:
        db_columns.setdefault(row["table_name"], set()).add(row["column_name"])

    problems = diff(db_columns)
    if not problems:
        print("DRIFT: (无)")
        return 0
    print("DRIFT:")
    for item in problems:
        print(f" - {item}")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
