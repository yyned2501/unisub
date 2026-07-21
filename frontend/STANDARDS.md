# UniSub 前端规范（Claude Code 专属）

> 本文档是 Claude Code 修改 UniSub 前端代码时的**行为准则**。
> 所有前端修改必须完全遵守以下规范，否则视为不合格。
>
> **Soybean Admin 参考：** `SOYBEAN_REFERENCE.md` 列出了 `/home/hermes/projects/soybean-admin` 项目中可借鉴的模块（请求封装、hooks、组件、store 模式等）。
> 开发新功能时优先参考，避免重复造轮子。

---

## 1. 技术栈

| 项 | 规范 |
|:---|:---|
| 框架 | Vue 3 Composition API |
| UI 库 | **Naive UI** |
| 样式 | **UnoCSS**（原子化 CSS）+ RemixIcon |
| 状态管理 | Pinia |
| 路由 | Vue Router 4，懒加载 |
| HTTP | Axios，统一拦截器（`service/request.js`） |
| UI 语言 | 中文 |

## 2. 设计原则（DRY + 组件化）

1. **DRY（Don't Repeat Yourself）**：相同的逻辑/UI 只写一次。发现重复立即抽成组件或 composable。
2. **组件化**：页面内容尽量拆成小组件，每个组件只做一件事（Single Responsibility）。
3. **解耦**：业务逻辑不进组件。API 调用、状态管理、工具函数分别归入 `service/api/`、`store/`、`utils/`，组件只管渲染和事件。
4. **布局**：侧边栏、导航栏直接在 `App.vue` 中定义，页面通过 `router-view` 渲染内容区。

## 3. 目录结构

```
frontend/
├── src/
│   ├── App.vue                # 入口页面（含侧边栏 + 导航栏 + 布局）
│   ├── main.js                # 入口
│   ├── plugins/               # 插件初始化
│   │   ├── assets.ts          # 资源加载（UnoCSS、RemixIcon 等）
│   │   └── index.ts
│   ├── router/
│   │   └── index.js           # 路由定义（懒加载）
│   ├── service/               # API 层（与后端 router 一一对应）
│   │   ├── request.js         # Axios 实例 + 统一拦截器
│   │   └── api/
│   │       ├── dashboard.js
│   │       ├── cd2.js
│   │       ├── emby.js
│   │       ├── platforms.js
│   │       ├── search.js
│   │       ├── subscriptions.js
│   │       └── tasks.js
│   ├── store/                 # Pinia 仓库
│   │   └── modules/
│   │       ├── app.js         # 全局状态（平台列表、看板统计）
│   │       └── theme.js       # 主题状态（暗色/亮色切换）
│   ├── components/            # 可复用组件
│   │   ├── common/            # 全局通用组件
│   │   │   └── app-provider.vue
│   │   ├── MediaCard.vue
│   │   ├── PlatformStatus.vue
│   │   ├── StatusBadge.vue
│   │   └── SubDialog.vue
│   ├── views/                 # 页面组件（每个路由对应一个页面）
│   │   ├── DashboardView.vue
│   │   ├── SearchView.vue
│   │   ├── SubscriptionsView.vue
│   │   └── settings/
│   │       ├── PlatformSettings.vue
│   │       ├── TaskSettings.vue
│   │       └── EmbyAnalysis.vue
│   └── styles/
│       └── css/
│           └── reset.css
├── Dockerfile
└── nginx.conf
```

## 4. 编码约定

| 层 | 职责 | 禁止 |
|:---|:---|:---|
| `views/` | 页面骨架，引用子组件，传递 props | 写业务逻辑、直接调 API |
| `components/` | 纯 UI，接收 props，emit 事件 | 调 store、调 API |
| `service/api/` | 封装 Axios 请求，返回 Promise | 处理 UI 状态 |
| `store/` | 跨组件共享状态 | 存组件私有数据 |

### 具体规则

- 使用 **Naive UI** 组件，保持风格统一
- 样式优先使用 **UnoCSS 原子化 class**（`flex`, `items-center`, `p-4`, `text-sm` 等），复杂样式用 `<style scoped>`
- 图标使用 **RemixIcon**（`<i class="ri-xxx-line"></i>`），不要引入其他图标库
- 页面内容按功能拆成 `components/` 下的小组件，`views/` 只做组装
- API 错误统一在 Axios 拦截器处理
- 路由使用异步懒加载（`() => import(...)`）
- 状态管理走 Pinia，不在组件内直接修改共享状态
- 暗色模式通过 `themeStore` 统一管理，使用 Naive UI 的 `darkTheme`
- 文件命名：Vue 组件用 PascalCase（`DashboardView.vue`），JS/TS 模块用 kebab-case（`request.js`）

## 5. 路由规范

```javascript
const routes = [
  {
    path: '/',
    name: 'Dashboard',
    component: () => import('../views/DashboardView.vue'),
    meta: { title: '看板' },
  },
]

router.afterEach((to) => {
  const title = to.meta?.title
  if (title) {
    document.title = `${title} — UniSub`
  }
})
```

- 使用 hash 模式（`createWebHashHistory`）
- 每个路由注册 `meta.title`（中文）
- 路由 name 用英文 PascalCase，与组件名一致
- `afterEach` 统一设置页面标题

## 6. API 层规范

```javascript
// service/api/xxx.js — 每个后端 router 对应一个文件
import request from '../request'

export function getPlatforms() {
  return request.get('/platforms')
}

export function updatePlatform(id, data) {
  return request.put(`/platforms/${id}`, data)
}
```

- 每个文件导出命名函数
- 路径相对于 `/api` 前缀（已在 `request.js` 中通过 proxy 统一配置）
- 函数名用 camelCase
- 不处理 UI 状态（loading/error），只返回 Promise