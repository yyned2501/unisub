"""日志查看路由 — 列出日志文件、读取内容。"""

import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import get_current_user
from app.core.logger import init_logger

router = APIRouter(prefix="/api/logs", tags=["日志查看"], dependencies=[Depends(get_current_user)])
logger = init_logger(__name__)

LOGS_DIR = Path(__file__).parent.parent.parent / "logs"

# 日志级别层级
LEVEL_MAP = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3}
_LOG_LEVEL_RE = re.compile(r"\[(DEBUG|INFO|WARNING|ERROR)\]")

def _parse_level(line: str) -> int | None:
    """从日志行提取级别数值（数字越大越严重）。"""
    m = _LOG_LEVEL_RE.search(line)
    if m:
        return LEVEL_MAP.get(m.group(1), 1)
    return None


@router.get("/files")
async def list_log_files():
    """列出 logs/ 目录下的日志文件（含大小和修改时间）。"""
    files = []
    if not LOGS_DIR.exists():
        return {"files": []}
    for f in sorted(LOGS_DIR.iterdir(), key=lambda x: x.name, reverse=True):
        if f.is_file():
            files.append({
                "name": f.name,
                "size": f.stat().st_size,
                "mtime": f.stat().st_mtime,
            })
    return {"files": files}


@router.get("/content")
async def get_log_content(
    file: str = Query("unisub.log", description="日志文件名"),
    lines: int = Query(200, ge=10, le=5000, description="返回行数"),
    filter: str = Query("", description="关键字筛选"),
    level: str = Query("DEBUG", description="最低日志级别: DEBUG, INFO, WARNING, ERROR"),
    tail: bool = Query(True, description="是否从末尾读取"),
):
    """读取日志文件内容，支持 tail、关键字和级别筛选。"""
    file_path = LOGS_DIR / file
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="日志文件不存在")
    if file_path.suffix not in (".log",):
        raise HTTPException(status_code=400, detail="仅支持 .log 文件")

    min_level = LEVEL_MAP.get(level.upper(), 0)

    try:
        raw = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取日志失败: {e}")

    all_lines = raw.splitlines()

    # 级别筛选
    if min_level > 0:
        all_lines = [ln for ln in all_lines if (_parse_level(ln) or 0) >= min_level]

    # 关键字筛选
    if filter:
        all_lines = [ln for ln in all_lines if filter in ln]

    # 取尾部 N 行
    if tail and len(all_lines) > lines:
        all_lines = all_lines[-lines:]

    return {
        "file": file,
        "total_lines": len(all_lines),
        "lines": all_lines,
    }


@router.get("/debug")
async def get_debug_info():
    """获取调试信息（环境变量、配置等）。"""
    import app.config as cfg
    config = cfg.parse_config()
    return {
        "debug": config.debug,
        "database_url": config.database_url,
        "cors_origins": config.cors_origins,
        "log_dir": str(LOGS_DIR),
        "log_dir_exists": LOGS_DIR.exists(),
        "log_files": [f.name for f in LOGS_DIR.iterdir() if f.is_file()] if LOGS_DIR.exists() else [],
    }