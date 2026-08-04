"""后台调度器 — 定时执行 Emby 轻量刷新和全量扫描。

支持双层次扫描:
  - 轻量刷新 (light scan): sync-cache + 补充缺失 TMDB 数据, 默认 10 分钟
  - 全量扫描 (full scan): sync-cache + 全量 TMDB + 同步订阅, 默认 60 分钟

配置由本模块管理，外部通过 get_task_config / update_task_config 读写。
"""

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path

from croniter import croniter

from app.core.logger import init_logger

logger = init_logger()

_scheduler_task: asyncio.Task | None = None
_stop_event: asyncio.Event | None = None
_auto_subscribe_runner: Callable[[], Awaitable[None]] | None = None
_auto_subscribe_last_slot: str | None = None
_tmdb_sync_runner: Callable[[], Awaitable[None]] | None = None

# 状态文件路径
_STATE_FILE = Path(__file__).parent.parent / "data" / "scheduler_state.json"

# 调度配置（内存存储，由 routers/tasks.py 通过 API 修改）
_task_config: dict = {
    "interval_minutes": 60,
    "light_interval_minutes": 10,
    "sync_interval_minutes": 60,
    "tmdb_interval_minutes": 60,
    "mp_supplement_enabled": True,
    "auto_sync_enabled": True,
}


async def start(
    light_scan_runner: Callable[[], Awaitable[None]],
    full_scan_runner: Callable[[], Awaitable[None]],
    auto_subscribe_runner: Callable[[], Awaitable[None]] | None = None,
    sync_runner: Callable[[], Awaitable[None]] | None = None,
    tmdb_sync_runner: Callable[[], Awaitable[None]] | None = None,
) -> None:
    """启动后台调度循环。"""
    global _scheduler_task, _stop_event, _auto_subscribe_runner, _tmdb_sync_runner

    _auto_subscribe_runner = auto_subscribe_runner
    _tmdb_sync_runner = tmdb_sync_runner

    if _scheduler_task is not None and not _scheduler_task.done():
        logger.warning("调度器已在运行中")
        return

    _stop_event = asyncio.Event()
    _scheduler_task = asyncio.create_task(
        _loop(
            light_scan_runner,
            full_scan_runner,
            auto_subscribe_runner,
            sync_runner,
            tmdb_sync_runner,
            _stop_event,
        )
    )
    logger.info("后台调度器已启动")


async def stop():
    """停止后台调度循环。"""
    global _scheduler_task

    if _scheduler_task is None or _scheduler_task.done():
        return

    if _stop_event:
        _stop_event.set()

    _scheduler_task.cancel()
    try:
        await _scheduler_task
    except asyncio.CancelledError:
        pass

    _scheduler_task = None
    logger.info("后台调度器已停止")


def load_state():
    """从 JSON 文件加载调度状态到内存。

    只接受已知配置项，丢弃历史遗留键（如已下线功能的残留配置）。
    """
    if not _STATE_FILE.exists():
        logger.info("调度状态文件不存在，使用默认配置")
        return

    try:
        raw = _STATE_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
        config = data.get("config")
        if isinstance(config, dict):
            known = {key: value for key, value in config.items() if key in _task_config}
            dropped = sorted(set(config) - set(known))
            if dropped:
                logger.info("调度状态忽略未知配置项: %s", dropped)
            _task_config.update(known)
        logger.info("调度状态已从文件加载: config=%s", _task_config)
    except (json.JSONDecodeError, OSError, TypeError) as e:
        logger.warning(f"调度状态文件解析失败: {e}，使用默认配置")


def save_state():
    """将内存中的调度状态持久化到 JSON 文件。"""
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "config": dict(_task_config),
        }
        _STATE_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.debug("调度状态已持久化到文件")
    except OSError as e:
        logger.error(f"调度状态持久化失败: {e}")


def get_task_config() -> dict:
    """获取当前调度任务配置的副本。"""
    return dict(_task_config)


def update_task_config(updates: Mapping[str, object]) -> dict:
    """合并更新调度任务配置并持久化。

    Args:
        updates: 局部配置更新项

    Returns:
        更新后的完整配置副本
    """
    _task_config.update(updates)
    save_state()
    logger.info("任务配置已更新: %s", _task_config)
    return dict(_task_config)


async def _run_auto_subscribe_if_due(
    runner: Callable[[], Awaitable[None]],
) -> None:
    """在 cron 槽位命中时触发自动订阅，避免同一分钟重复运行。"""
    global _auto_subscribe_last_slot

    from app.services.auto_subscribe.config_store import get_config_store

    config = get_config_store().load_config()
    if not config.get("enabled"):
        return
    source_names = ("douban", "mikan", "netflix", "maoyan")
    if not any(config.get(f"{name}_enabled") for name in source_names):
        return

    schedule = str(config.get("schedule_cron") or "")
    if not croniter.is_valid(schedule):
        logger.error("自动订阅 cron 无效，已跳过: %s", schedule)
        return

    now = datetime.now(UTC).replace(second=0, microsecond=0)
    slot = now.isoformat()
    if slot == _auto_subscribe_last_slot:
        return
    if not croniter.match(schedule, now):
        return

    _auto_subscribe_last_slot = slot
    logger.info("调度器触发自动订阅: cron=%s", schedule)
    await runner()


async def _loop(
    light_scan_runner: Callable[[], Awaitable[None]],
    full_scan_runner: Callable[[], Awaitable[None]],
    auto_subscribe_runner: Callable[[], Awaitable[None]] | None,
    sync_runner: Callable[[], Awaitable[None]] | None,
    tmdb_sync_runner: Callable[[], Awaitable[None]] | None,
    stop_event: asyncio.Event,
) -> None:
    """调度主循环，按需触发扫描、同步与自动订阅。"""
    _last_light_run: datetime | None = None
    _last_full_run: datetime | None = None
    _last_sync_run: datetime | None = None
    _last_tmdb_sync_run: datetime | None = None

    while not stop_event.is_set():
        try:
            enabled = _task_config.get("auto_sync_enabled", True)
            light_interval = _task_config.get("light_interval_minutes", 10)
            full_interval = _task_config.get("interval_minutes", 60)
            sync_interval = _task_config.get("sync_interval_minutes", 60)
            tmdb_interval = _task_config.get("tmdb_interval_minutes", 60)

            if enabled:
                now = datetime.now(UTC)

                # 检查是否需要全量扫描（优先级高）
                if _last_full_run is None or (now - _last_full_run).total_seconds() >= full_interval * 60:
                    from app.services.emby_scan import EmbyScanService

                    status = EmbyScanService.get_status()
                    if not status["running"]:
                        logger.info(f"调度器触发全量扫描: 间隔 {full_interval} 分钟")
                        await full_scan_runner()
                        _last_full_run = datetime.now(UTC)
                        _last_light_run = _last_full_run  # 全量包含轻量，重置轻量计时
                        _last_sync_run = _last_full_run  # 全量包含 NF 同步，重置同步计时
                        _last_tmdb_sync_run = _last_full_run  # 全量包含 TMDB 刷新，重置计时
                    else:
                        logger.debug("调度器跳过: 扫描正在运行中")
                    await asyncio.sleep(0)  # 让出控制权
                    continue

                # 检查是否需要轻量刷新
                if _last_light_run is None or (now - _last_light_run).total_seconds() >= light_interval * 60:
                    from app.services.emby_scan import EmbyScanService

                    status = EmbyScanService.get_status()
                    if not status["running"]:
                        logger.info(f"调度器触发轻量刷新: 间隔 {light_interval} 分钟")
                        await light_scan_runner()
                        _last_light_run = datetime.now(UTC)
                    else:
                        logger.debug("调度器跳过: 扫描正在运行中")

                # 检查是否需要 NF 订阅同步
                if sync_runner and (
                    _last_sync_run is None or (now - _last_sync_run).total_seconds() >= sync_interval * 60
                ):
                    logger.info(f"调度器触发 NF 订阅同步: 间隔 {sync_interval} 分钟")
                    await sync_runner()
                    _last_sync_run = datetime.now(UTC)

                # 检查是否需要 TMDB 增量刷新
                if tmdb_sync_runner and (
                    _last_tmdb_sync_run is None or (now - _last_tmdb_sync_run).total_seconds() >= tmdb_interval * 60
                ):
                    logger.info(f"调度器触发 TMDB 增量刷新: 间隔 {tmdb_interval} 分钟")
                    await tmdb_sync_runner()
                    _last_tmdb_sync_run = datetime.now(UTC)

            if auto_subscribe_runner:
                await _run_auto_subscribe_if_due(auto_subscribe_runner)

        except Exception as e:
            logger.error(f"调度器循环异常: {e}")

        # 每 10 秒检查一次，同时响应 stop_event
        for _ in range(2):
            if stop_event.is_set():
                return
            await asyncio.sleep(5)
