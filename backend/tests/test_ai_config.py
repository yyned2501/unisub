"""AI 配置存储测试。"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.ai_config import DEFAULT_AI_CONFIG, AiConfigStore
from app.services.auto_subscribe.config_store import AutoSubscribeConfigStore


def test_load_missing_ai_config_uses_defaults(tmp_path: Path) -> None:
    """独立 AI 配置文件不存在时应返回默认值。"""
    store = AiConfigStore(
        config_path=tmp_path / "ai_config.json",
        legacy_config_path=tmp_path / "auto_subscribe_config.json",
    )

    assert store.load_config() == DEFAULT_AI_CONFIG


def test_save_ai_config_preserves_unspecified_fields(tmp_path: Path) -> None:
    """局部保存 AI 配置不应丢失已存在字段。"""
    store = AiConfigStore(config_path=tmp_path / "ai_config.json")
    store.save_config({"ai_api_base": "https://example.test", "ai_api_key": "secret"})

    saved = store.save_config({"ai_assist_enabled": True})

    assert saved["ai_assist_enabled"] is True
    assert saved["ai_api_base"] == "https://example.test"
    assert saved["ai_api_key"] == "secret"


def test_ai_config_migrates_legacy_fields(tmp_path: Path) -> None:
    """首次加载应将旧自动订阅配置中的 AI 字段迁移到独立文件。"""
    ai_path = tmp_path / "ai_config.json"
    legacy_path = tmp_path / "auto_subscribe_config.json"
    legacy_path.write_text(
        json.dumps({"enabled": True, "ai_assist_enabled": True, "ai_model": "test-model"}),
        encoding="utf-8",
    )
    store = AiConfigStore(config_path=ai_path, legacy_config_path=legacy_path)

    config = store.load_config()

    assert config["ai_assist_enabled"] is True
    assert config["ai_model"] == "test-model"
    assert "ai_assist_enabled" not in json.loads(legacy_path.read_text(encoding="utf-8"))
    assert json.loads(legacy_path.read_text(encoding="utf-8"))["enabled"] is True


def test_auto_subscribe_partial_update_preserves_existing_fields(tmp_path: Path) -> None:
    """回归：局部自动订阅更新不得将未提交字段重置为默认值。"""
    store = AutoSubscribeConfigStore(config_path=tmp_path / "auto_subscribe_config.json")
    store.save_config({"enabled": True, "min_year": 2025, "schedule_cron": "8 */8 * * *"})

    saved = store.save_config({"min_vote": 5.5})

    assert saved["enabled"] is True
    assert saved["min_year"] == 2025
    assert saved["min_vote"] == 5.5
    assert saved["schedule_cron"] == "8 */8 * * *"
