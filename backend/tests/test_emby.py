"""Emby 服务测试 — 按季集数聚合逻辑（sync_cache 的核心统计）。"""

from app.services.emby.cache_sync import aggregate_episodes


def test_aggregate_episodes_counts_per_series_and_season():
    """应按 SeriesId 统计整剧集数、按 ParentIndexNumber 统计按季集数。"""
    eps = [
        {"SeriesId": "A", "ParentIndexNumber": 1, "IndexNumber": 1},
        {"SeriesId": "A", "ParentIndexNumber": 1, "IndexNumber": 2},
        {"SeriesId": "A", "ParentIndexNumber": 2, "IndexNumber": 1},
        {"SeriesId": "B", "ParentIndexNumber": 1, "IndexNumber": 1},
    ]
    episode_counts, season_counts = aggregate_episodes(eps)
    assert episode_counts == {"A": 3, "B": 1}
    assert season_counts == {"A": {1: 2, 2: 1}, "B": {1: 1}}


def test_aggregate_episodes_skips_missing_series_id():
    """无 SeriesId 的项不计入任何统计。"""
    eps = [
        {"ParentIndexNumber": 1, "IndexNumber": 1},  # 无 SeriesId
        {"SeriesId": "A", "ParentIndexNumber": 1, "IndexNumber": 1},
    ]
    episode_counts, season_counts = aggregate_episodes(eps)
    assert episode_counts == {"A": 1}
    assert season_counts == {"A": {1: 1}}


def test_aggregate_episodes_skips_special_season():
    """特典季（ParentIndexNumber=0）与缺季号项计入整剧但不计入按季。"""
    eps = [
        {"SeriesId": "A", "ParentIndexNumber": 0, "IndexNumber": 1},  # 特典季
        {"SeriesId": "A", "IndexNumber": 2},  # 无季号
        {"SeriesId": "A", "ParentIndexNumber": 1, "IndexNumber": 3},
    ]
    episode_counts, season_counts = aggregate_episodes(eps)
    assert episode_counts == {"A": 3}  # 整剧三集都算
    assert season_counts == {"A": {1: 1}}  # 按季只统计第1季


def test_aggregate_episodes_empty():
    """空列表返回空统计。"""
    assert aggregate_episodes([]) == ({}, {})
