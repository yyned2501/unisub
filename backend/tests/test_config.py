"""配置模块测试 — 验证环境变量解析逻辑。"""

import os
from unittest.mock import patch

from app.config import parse_config


def test_parse_config_defaults():
    """默认配置应返回合理默认值。"""
    with patch.dict(os.environ, {}, clear=True):
        config = parse_config()
    assert config.debug is False
    assert "postgresql" in config.database_url
    assert isinstance(config.cors_origins, list)
    assert len(config.cors_origins) >= 1


def test_parse_config_debug_enabled():
    """UNISUB_DEBUG=true 应启用调试模式。"""
    with patch.dict(os.environ, {"UNISUB_DEBUG": "true"}):
        config = parse_config()
    assert config.debug is True


def test_parse_config_custom_database_url():
    """自定义数据库 URL 应被正确读取。"""
    url = "sqlite+aiosqlite:///:memory:"
    with patch.dict(os.environ, {"UNISUB_DATABASE_URL": url}):
        config = parse_config()
    assert config.database_url == url


def test_parse_config_cors_origins_json():
    """CORS 来源应从 JSON 数组解析。"""
    origins = '["http://a.com","http://b.com"]'
    with patch.dict(os.environ, {"UNISUB_CORS_ORIGINS": origins}):
        config = parse_config()
    assert config.cors_origins == ["http://a.com", "http://b.com"]


def test_parse_config_cors_origins_invalid_json():
    """无效 JSON 应回退到默认值。"""
    with patch.dict(os.environ, {"UNISUB_CORS_ORIGINS": "not-json"}):
        config = parse_config()
    assert "http://localhost:5173" in config.cors_origins


def test_parse_config_proxy_url():
    """代理 URL 应可选读取。"""
    with patch.dict(os.environ, {"UNISUB_PROXY_URL": "http://proxy:8080"}):
        config = parse_config()
    assert config.proxy_url == "http://proxy:8080"


def test_parse_config_proxy_url_absent():
    """未设置代理时应为 None。"""
    with patch.dict(os.environ, {}, clear=True):
        config = parse_config()
    assert config.proxy_url is None
