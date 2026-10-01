"""测试隔离守护 — 断言测试进程从未绑定生产数据库。

这是「测试不得触碰生产 DB」这条红线的回归测试：任何把 conftest 的
硬赋值改回 setdefault、或在别处提前导入 app 的改动都会在这里炸掉。
"""

from app.core.database import engine


def test_app_engine_points_to_test_database():
    """app.core.database 的引擎必须指向 sqlite 内存库，不得是 PostgreSQL。"""
    assert engine.url.get_backend_name() == "sqlite", (
        f"测试进程的应用引擎指向了 {engine.url.render_as_string(hide_password=True)} —— "
        "说明 UNISUB_DATABASE_URL 被外部环境（如 source backend/.env）穿透，测试会写生产库"
    )


def test_app_engine_url_is_memory():
    """连接串必须是内存库，避免测试残留落到磁盘文件。"""
    assert ":memory:" in str(engine.url)
