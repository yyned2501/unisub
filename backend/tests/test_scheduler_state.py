"""调度器状态文件加载测试。"""

from __future__ import annotations

import json

from app.services import scheduler


def test_load_state_filters_unknown_keys(tmp_path, monkeypatch):
    """状态文件中的未知配置项（已下线功能残留）不应进入运行配置。"""
    state_file = tmp_path / "scheduler_state.json"
    state_file.write_text(
        json.dumps(
            {
                "config": {
                    "interval_minutes": 30,
                    "auto_fill_enabled": True,  # 已下线功能的残留键
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(scheduler, "_STATE_FILE", state_file)
    monkeypatch.setattr(scheduler, "_task_config", {**scheduler._task_config, "interval_minutes": 60})

    scheduler.load_state()

    assert scheduler._task_config["interval_minutes"] == 30
    assert "auto_fill_enabled" not in scheduler._task_config


def test_load_state_missing_file_keeps_defaults(tmp_path, monkeypatch):
    """状态文件不存在时保持默认配置。"""
    monkeypatch.setattr(scheduler, "_STATE_FILE", tmp_path / "not_exist.json")
    monkeypatch.setattr(scheduler, "_task_config", dict(scheduler._task_config))
    before = dict(scheduler._task_config)

    scheduler.load_state()

    assert scheduler._task_config == before
