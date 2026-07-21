# UniSub 项目规范（Claude Code 专属）

> 本文档是 Claude Code 修改 UniSub 代码时的**唯一行为准则**。
> 任何新增功能或代码修改必须完全遵守以下规范，否则视为不合格。

---

## 0. 设计哲学

```
用户搜索 TMDB → 点「订阅」→ 记录到本地 + 推给 NextFind
                                ↓
                   定时任务轮询 NF 订阅状态
                   发现缺集 → 触发 NF fill_missing 补下载
                   无法补的 → 调 MoviePilot 兜底搜索
```

**定位：**
- **UniSub 是订阅决策层** — 搜索、添加、管理订阅
- **NextFind 是主力执行层** — 搜索资源 + 转存网盘 + 追更
- **MoviePilot 是兜底补充层** — 仅定时任务触发搜索 API
- **不取代任何平台**，只做"指挥 + 聚合"

---

## 1. 架构铁律（三层解耦）

### 1.1 分层

```
routers/  →  只调 services/，不做业务逻辑
services/ →  只从 core/ 和 models/ 导入
core/     →  唯一可直接 import 第三方库的层
```

### 1.2 目录结构

```
backend/app/
├── main.py              # FastAPI 入口，只做生命周期
├── config.py            # 配置 dataclass + parse_config()
├── core/
│   ├── __init__.py      # 统一导出（Base, async_session, get_db, http_client, init_logger）
│   ├── database.py      # SQLAlchemy async engine + session factory
│   ├── http_client.py   # httpx.AsyncClient 封装
│   └── logger.py        # logging 封装（禁止 print）
├── models/
│   ├── __init__.py      # 统一导出所有 ORM 模型
│   ├── platform_config.py
│   ├── subscription.py
│   ├── activity_log.py
│   ├── cd2_config.py
│   ├── emby_cache.py
│   └── emby_blacklist.py
├── schemas/
│   ├── __init__.py      # 统一导出所有 Pydantic schemas
│   ├── platform.py
│   ├── subscription.py
│   ├── search.py
│   ├── cd2.py
│   ├── dashboard.py
│   ├── emby.py
│   └── emby_cache.py
├── services/
│   ├── __init__.py      # 统一导出 + 工厂函数（get_nf/mp/emby/tmdb_service）
│   ├── nextfind.py      # NextFind OpenAPI 封装
│   ├── nextfind_admin.py # NextFind 管理类 API 封装
│   ├── moviepilot.py    # MoviePilot REST API 封装
│   ├── orchestrator.py  # 编排逻辑（订阅、取消、双向同步、MP 补充）
│   ├── tmdb.py          # TMDB API v3 封装
│   ├── emby.py          # Emby REST API 封装 + 缓存同步
│   ├── emby_scan.py     # Emby 一键扫描服务（三步全流程 + 进度跟踪）
│   ├── emby_db.py       # Emby 数据库操作封装（缺集分析、黑名单）
│   ├── subscription.py  # 订阅数据库操作封装
│   ├── dashboard.py     # 看板数据库操作封装
│   ├── platform.py      # 平台配置 CRUD 操作封装
│   ├── cd2_config.py    # CloudDrive2 配置持久化
│   ├── clouddrive2.py   # CloudDrive2 gRPC 服务封装
│   └── scheduler.py     # 后台调度器（轻量刷新 + 全量扫描计时循环）
├── routers/
│   ├── __init__.py      # 统一导出所有 router
│   ├── platforms.py     # 平台配置 CRUD
│   ├── cd2.py           # CloudDrive2 设置与连接测试
│   ├── search.py        # 搜索
│   ├── subscriptions.py # 订阅管理
│   ├── dashboard.py     # 看板
│   ├── emby.py          # Emby 媒体库（缺集分析、缓存同步、黑名单）
│   └── tasks.py         # 定时任务管理
└── references/          # 外部 API 文档参考
    └── nextfind-api-v2.md
```

### 1.3 禁止行为（铁律）

| ❌ 禁止 | 原因 |
|:---|:---|
| `from sqlalchemy import ...` **在 core/ 以外** | 第三方库只能在 core/ |
| `from httpx import ...` **在 core/ 以外** | 同上 |
| `from services/nextfind import ...` **在 routers/ 之外** | routers 调 services，反向不行 |
| `from models import ...` **在 routers/ 或 core/ 里** | 只有 services/ 能调 models |
| `from routers import ...` **在 services/ 里** | routers 是入口层，不应被反向引用 |

### 1.4 跨模块修改影响表

修改以下文件时，必须同步检查：

| 改这个 | 检查这些 |
|:---|:---|
| `core/database.py` | `core/http_client.py`, `models/*`, `services/orchestrator.py` |
| `config.py` | `core/*`, `services/nextfind.py`, `services/moviepilot.py` |
| `services/nextfind.py` | `routers/subscriptions.py`, `services/orchestrator.py` |
| `models/subscription.py` | `schemas/subscription.py`, `services/orchestrator.py` |

---

## 2. Python 规范

### 2.1 基础

| 项 | 规范 |
|:---|:---|
| 版本 | Python 3.13+ |
| 包管理 | `uv`（阿里源镜像 `mirrors.aliyun.com`） |
| 运行 | `uv run python3 -m app.main` |
| 依赖声明 | `pyproject.toml` |
| 异步 | 全栈 async，禁止阻塞调用 |

### 2.2 代码风格

```python
# ✅ 必须：类型注解 + 中文 docstring
async def get_subscriptions(db: AsyncSession, user_id: int) -> list[Subscription]:
    """获取用户的所有订阅列表"""
    ...

# ❌ 禁止：无类型注解、英文或无 docstring
def get_subs(db, uid):
    ...

# ❌ 禁止：print
print("server started")  # 错误
logger.info("服务启动完成")  # 正确

# ❌ 禁止：阻塞调用
time.sleep(1)  # 错误
await asyncio.sleep(1)  # 正确
```

#### 细则

- **类型注解**：所有函数参数和返回值必须有完整类型注解。使用 `list[...]` / `dict[...]` 等泛型表达式，不用 `List[...]` / `Dict[...]` 等 typing 旧风格（Python 3.9+ 内置泛型）。
- **中文 docstring**：每个公共函数/方法必须带中文 docstring，说明功能、参数、返回值。单行 docstring 用 `"""..."""` 三引号，多行则首行概述+空行+详情。
- **<300 行/文件**：超过必须拆模块，放到 `xxx/` 子目录下的多文件（`__init__.py` + 模块文件）。
- **`__init__.py`**：每个 Python 包必须有 `__init__.py`，统一导出公开接口。
- **绝对导入**：跨文件引用使用绝对导入（`from app.services.nextfind import ...`），禁止模糊相对引用。

### 2.3 日志

```python
# ✅ 正确
from app.core.logger import logger
logger.info("订阅状态同步完成: %d 条", count)
logger.error("NextFind API 调用失败: %s", exc_info=e)

# ❌ 禁止
print("xxx")
```

- 所有日志输出必须用 `app.core.logger`。
- log 级别：`info` 用于常规流程，`warning` 用于可恢复异常，`error` 用于不可恢复故障。

---

## 3. 数据库规范

### 3.1 模型定义

- **SQLAlchemy async ORM**（声明式模型）
- **模型名单数形式**：`PlatformConfig`, `Subscription`, `ActivityLog`
- **表名小写复数**：`platform_configs`, `subscriptions`, `activity_logs`
- **UUID PK**：所有表使用 UUID 主键
- **自动时间戳**：`created_at` 和 `updated_at` 字段用 `server_default` + `onupdate`

```python
# 模板
class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    tmdb_id: Mapped[int]
    title: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

### 3.2 Session 管理

- 使用 `async_scoped_session` 或 `AsyncSession` + `async with` 模式
- **禁止**同步 session，全栈 async
- 连接串从 `config.py` 读取

### 3.3 命名规范

```python
# 模型：单数
class PlatformConfig(Base):   # ✅
class PlatformConfigs(Base):  # ❌

# Pydantic 模式：复数 + 用途后缀
class PlatformConfigCreate(BaseModel):     # ✅
class SubscriptionResponse(BaseModel):     # ✅
class PlatformConfig(BaseModel):           # ❌ 用途不清
```

---

## 4. 外部 API 规范

### 4.1 对接规则

- 所有外部 API 封装在 `services/` 层
- 第三方 HTTP 客户端统一走 `core/http_client.py`（httpx.AsyncClient）
- 每个外部平台一个独立 service 文件
- Service 类方法必须：① 返回 Python 对象（dict/type），不丢 raw response；② 失败抛带上下文的异常

### 4.2 外部 API 文档参考

见以下文件（Claude Code 修改前必读）：

| 文件 | 内容 |
|:---|:---|
| `references/nextfind-api-v2.md` | NextFind OpenAPI + Web API 全部端点实测结果、参数坑、缺集逻辑 |
| `CLAUDE.md` | NextFind 登录凭据、MoviePilot 基础配置 |

### 4.3 NextFind 关键坑

- `tmdb_id` 传**字符串**，不要传 int
- `POST /media/fill_missing` 触发补缺下载，返回 `{"status":"success","message":"补缺任务已提交队列"}`
- `GET /api/local_library?type=tv&tmdb_id=`（Web API，需 cookie 登录）才是正确的缺集查询方式
- `local_library/filter`（OpenAPI）全线 500，不可用

---

## 5. Router 规范

```python
from fastapi import APIRouter, Depends, HTTPException
from app.services.subscriptions import SubscriptionService

router = APIRouter(prefix="/api/subscriptions", tags=["订阅管理"])

@router.get("")
async def list_subscriptions(...):
    """获取所有订阅列表"""
    ...

@router.post("", status_code=201)
async def create_subscription(...):
    """添加新订阅"""
    ...
```

- 每个 router 对应一个功能模块
- `prefix="/api/..."` + `tags=["..."]`（中文）
- 统一错误处理：`HTTPException` 带中文 message
- router 不包含业务逻辑，全部委托给 services/

---

---

## 6. 数据库表结构（当前）

### `platform_configs`

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| id | UUID PK | |
| name | str | 平台名（`nextfind` / `moviepilot`） |
| base_url | str | API 基地址 |
| api_key | str | 鉴权密钥 |
| enabled | bool | 是否启用（默认 true） |
| created_at | datetime | |
| updated_at | datetime | |

### `subscriptions`

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| id | UUID PK | |
| tmdb_id | int | TMDB ID |
| media_type | str | `movie` / `tv` |
| title | str | 标题 |
| poster_url | str | 海报 URL（可空） |
| year | int | 年份（可空） |
| nf_subscribed | bool | 是否已添加到 NextFind（默认 false） |
| nf_status | str | NextFind 状态（`active` / `missing_fill` / `completed`，可空） |
| nf_missing_eps | int | 缺集数（默认 0） |
| nf_sub_id | str | NextFind 订阅 ID（可空） |
| completed | bool | 是否完结（默认 false） |
| created_at | datetime | |
| updated_at | datetime | |

### `activity_logs`

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| id | UUID PK | |
| action | str | `subscribe` / `unsubscribe` / `mp_search` / `mp_downloaded` / `system` / `sync` |
| tmdb_id | int | 关联媒体 ID（可空） |
| message | str | 日志内容 |
| created_at | datetime | |

---

## 7. Git 规范

| 项 | 规范 |
|:---|:---|
| 提交信息 | 中文，conventional commit 格式 |
| 示例 | `feat: 添加统一搜索功能` / `fix: 修复 NextFind 缺集查询参数类型` |
| 分支 | `main` 为主干，`feature/*` 为功能分支 |
| 推送前 | 本地验证启动通过 + API 正常返回 |

---

## 8. 修改协议（改动前必读）

### 8.1 改动前

1. 先读本文件
2. 如果涉及跨模块调用变化，输出受影响文件清单
3. 涉及外部 API 对接，先读 `references/nextfind-api-v2.md`

### 8.2 改动中

1. 文档先行：改了接口/结构，先更新本文档再改代码
2. 严禁循环依赖（services → core → services），发现立即报告

### 8.3 改动后

1. `uv run python3 -c "from app import ..."` — 验证 import 通过
2. `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000` — 验证启动
3. `curl http://localhost:8000/api/platforms` — 返回 `[]` 或正常数据
4. 验证改动涉及的 API 返回正确
5. **前端有改动时**：`cd frontend && npm run build` — 构建前端
6. **后端有改动时**：`sudo systemctl restart unisub-backend` — 重启后端服务
   - 重启后等 3 秒再测试：`sleep 3 && curl http://localhost:8002/api/platforms`

---

## 9. 缺集数据流程（重要）

### 9.1 正确流程

```
1. Web API（cookie 登录）→ GET /api/local_library?type=tv&tmdb_id={id}
   → 返回逐集 is_aired + has_local
   → 真缺集 = is_aired == true AND has_local == false

2. 触发补下载 → OpenAPI POST /api/openapi/media/fill_missing
   Body: {"tmdb_id": "字符串", "media_type": "tv"}
   → 返回 {"status": "success", "message": "补缺任务已提交队列"}
```

### 9.2 不要做的事

- ❌ 不要用 `local_library/filter`（全线 500）
- ❌ 不要用 `total_episodes` 算缺集（那是全集数，不是已播出数）
- ❌ 不要依赖 TMDB API 获取已播出数据（Web API 自带 `is_aired`）
- ❌ `tmdb_id` 传 int 给 NextFind（要传字符串）

---

## 10. 运维常识

| 项 | 说明 |
|:---|:---|
| 开发启动 | `cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload` |
| systemd | `unisub-backend.service`，restart 后等 3 秒再测 |
| PG 连接 | `unisub:unisub@192.168.31.10:5432/unisub` |
| 前端 | Vue 3，构建后 nginx 托管 |
| 部署 | Docker Compose 上线 Tower（192.168.31.10） |