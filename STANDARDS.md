# UniSub 项目规范

## Python 规范

- **版本**: Python 3.13+
- **包管理**: uv（阿里源镜像）
- **代码风格**: 类型注解，中文 docstring，<300 行/文件
- **日志**: logging 替代 print，文件 + 控制台输出
- **配置**: dataclass + parse_config() 类型安全读取
- **数据库**: SQLAlchemy async + asyncpg，声明式模型
- **异步**: 全栈 async，禁止阻塞调用

## 架构规范

- **三层解耦**: routers → services → core（第三方库隔离）
- core/ 层是唯一直接 import 第三方库的地方（sqlalchemy, httpx, asyncpg）
- services/ 只从 core/ 和 models/ 导入
- routers/ 只调用 services/，不包含业务逻辑

## Vue 规范

- **框架**: Vue 3 Composition API + Element Plus
- **状态管理**: Pinia
- **路由**: Vue Router 4，懒加载
- **API 调用**: Axios，统一错误处理
- **UI 语言**: 中文

## Git 规范

- **提交信息**: 中文，conventional commit 格式
- **示例**: `feat: 添加统一搜索功能`
- **分支**: main 为主干，feature/* 为功能分支

## 文档

每个文件需要有：
- 模块级别的中文 docstring（描述功能）
- 公共函数的参数/返回值类型注解
- 复杂逻辑的内联注释