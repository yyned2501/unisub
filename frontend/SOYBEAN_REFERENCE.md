# Soybean Admin 参考手册

> Soybean Admin 项目路径：`/home/hermes/projects/soybean-admin`
>
> 当 UniSub 前端需要添加新功能时，优先参考此项目中的实现，避免重复造轮子。

---

## 1. 核心模块一览

| 模块 | 路径 | 说明 |
|:---|:---|:---|
| 请求封装 | `packages/axios/src/` | 基于 Axios 的请求封装，含拦截器、token 刷新、错误处理 |
| Hooks | `packages/hooks/src/` | 通用 hooks：useBoolean, useLoading, useCountDown, useRequest, useTable |
| 工具函数 | `packages/utils/src/` | 加密、存储、克隆、nanoid |
| 颜色工具 | `packages/color/src/` | 调色板、颜色计算 |
| 组件库 | `packages/materials/src/` | admin-layout, page-tab, simple-scrollbar |
| UnoCSS 预设 | `packages/uno-preset/src/` | 自定义 UnoCSS 预设 |

---

## 2. 可直接借鉴的模块

### 2.1 请求封装（最有用）

**路径：** `packages/axios/src/index.ts`

提供了 `createRequest` 和 `createFlatRequest` 两个工厂函数：
- 统一错误处理、token 刷新、重试逻辑
- `isBackendSuccess` / `onBackendFail` / `onError` 生命周期
- 支持 `logoutCodes`、`modalLogoutCodes`、`expiredTokenCodes` 三种错误码处理策略

**UniSub 已用：** `service/request.js` 是自己写的基础 Axios 封装。如果未来需要 token 刷新、重试等高级功能，直接参考 `@sa/axios` 的实现。

### 2.2 Hooks

**路径：** `packages/hooks/src/`

| Hook | 用途 | UniSub 是否可用 |
|:---|:---|:---|
| `useBoolean` | 布尔状态管理（`bool`, `setTrue`, `setFalse`, `toggle`） | ✅ 可直接用 |
| `useLoading` | Loading 状态管理 | ✅ 可直接用 |
| `useCountDown` | 倒计时 | ✅ 可抄 |
| `useRequest` | 请求封装（loading/data/error 状态） | ✅ 可抄 |
| `useTable` | 表格数据管理（分页、排序、筛选） | ⚠️ 偏重，按需借鉴 |

### 2.3 工具函数

**路径：** `packages/utils/src/`

| 工具 | 文件 | 说明 |
|:---|:---|:---|
| `createStorage` | `storage.ts` | localStorage/sessionStorage 封装，带前缀和 JSON 序列化 |
| `createLocalforage` | `storage.ts` | IndexedDB 封装 |
| `jsonClone` | `klona.ts` | 深拷贝（基于 klona） |
| `nanoid` | `nanoid.ts` | 唯一 ID 生成 |
| `encrypt` / `decrypt` | `crypto.ts` | AES 加解密 |

### 2.4 工具函数（src/utils/）

**路径：** `src/utils/`

| 文件 | 内容 | 说明 |
|:---|:---|:---|
| `service.ts` | `getServiceBaseURL` | 根据环境获取 API 基地址 |
| `storage.ts` | `localStg`, `sessionStg`, `localforage` | 存储实例（基于 `@sa/utils`） |
| `common.ts` | 通用工具函数 | 各种零散工具 |
| `icon.ts` | 图标相关 | SVG 图标渲染 |
| `agent.ts` | 用户代理检测 | 浏览器/设备检测 |

### 2.5 组件

**路径：** `src/components/`

| 组件 | 路径 | 说明 |
|:---|:---|:---|
| `AppProvider` | `common/app-provider.vue` | ✅ **UniSub 已移植** |
| `DarkModeContainer` | `common/dark-mode-container.vue` | 暗色模式容器，可参考 |
| `ExceptionBase` | `common/exception-base.vue` | 403/404/500 错误页 |
| `SystemLogo` | `common/system-logo.vue` | 系统 Logo |
| `ThemeSchemaSwitch` | `common/theme-schema-switch.vue` | 主题切换按钮 |
| `FullScreen` | `common/full-screen.vue` | 全屏切换 |
| `SvgIcon` | `custom/svg-icon.vue` | SVG 图标组件 |
| `CountTo` | `custom/count-to.vue` | 数字滚动动画 |
| `ButtonIcon` | `custom/button-icon.vue` | 图标按钮 |
| `BetterScroll` | `custom/better-scroll.vue` | 滚动优化 |

### 2.6 Store 模式

**路径：** `src/store/modules/`

| Store | 说明 |
|:---|:---|
| `app/index.ts` | 全局应用状态（侧边栏折叠、多语言、移动端适配、页面重载） |
| `theme/index.ts` | 主题管理（暗色/亮色/自动、布局模式、颜色、动画） |
| `auth/index.ts` | 认证状态（token、用户信息、权限） |
| `route/index.ts` | 路由和菜单管理 |
| `tab/index.ts` | 多标签页管理 |

**UniSub 已用：** `store/modules/app.js` 和 `store/modules/theme.js` 是简化版本。如需多标签页、路由权限等，参考 Soybean 的实现。

### 2.7 路由守卫

**路径：** `src/router/guard/`

| 守卫 | 说明 |
|:---|:---|
| `progress.ts` | 路由跳转进度条（NProgress） |
| `route.ts` | 路由鉴权（登录态检查、权限检查） |
| `title.ts` | 动态设置页面标题 |

**UniSub 已用：** `title.ts` 功能已在 `router/index.js` 的 `afterEach` 中实现。

### 2.8 布局组件

**路径：** `src/layouts/`

| 组件 | 说明 |
|:---|:---|
| `base-layout/index.vue` | 基础布局（侧边栏+头部+内容区） |
| `blank-layout/index.vue` | 空白布局（登录页等） |
| `modules/global-header/` | 头部组件（面包屑、搜索、用户信息、主题切换） |
| `modules/global-menu/` | 菜单组件（垂直/水平/混合模式） |
| `modules/global-tab/` | 多标签页 |
| `modules/global-sider/` | 侧边栏 |
| `modules/global-search/` | 全局搜索框 |
| `modules/theme-drawer/` | 主题设置抽屉 |

**UniSub 未用：** UniSub 的布局直接在 `App.vue` 中实现，较简单。如需高级布局（如多标签页、混合菜单），参考 `materials/src/libs/admin-layout/` 和 `layouts/` 下的实现。

### 2.9 页面组件

**路径：** `src/views/`

| 页面 | 说明 |
|:---|:---|
| `home/index.vue` | 首页看板（卡片数据、折线图、饼图） |
| `home/modules/card-data.vue` | 数据统计卡片 |
| `home/modules/line-chart.vue` | 折线图（ECharts） |
| `home/modules/pie-chart.vue` | 饼图（ECharts） |
| `_builtin/` | 403/404/500/登录/注册/重置密码 |

### 2.10 样式

**路径：** `src/styles/`

| 文件 | 说明 |
|:---|:---|
| `css/global.css` | 全局样式 |
| `css/reset.css` | ✅ **UniSub 已移植** |
| `css/transition.css` | 过渡动画 |
| `css/nprogress.css` | NProgress 样式 |
| `scss/global.scss` | SCSS 全局样式 |
| `scss/scrollbar.scss` | 滚动条样式 |

---

## 3. 与 UniSub 的差异对比

| 维度 | Soybean Admin | UniSub |
|:---|:---|:---|
| 请求库 | `@sa/axios`（二次封装） | 原生 Axios |
| 存储 | `@sa/utils`（localforage） | 原生 localStorage |
| 图标 | SvgIcon + Iconify | RemixIcon（`<i class="ri-xxx">`） |
| 样式 | UnoCSS + SCSS 模块 | UnoCSS + scoped CSS |
| 布局 | 复杂布局系统（多种模式） | 直接在 `App.vue` 中实现 |
| 多语言 | vue-i18n | 无（仅中文） |
| 路由 | 文件系统路由（elegant router） | 手动定义 |
| 类型 | 全套 TypeScript | JavaScript |

---

## 4. 常见移植场景

### 场景：需要表格分页功能

Soybean 的 `useNaiveTable` / `useNaivePaginatedTable`（`hooks/common/table.ts`）提供了完整的 Naive UI 表格封装，包括：
- 分页、排序、筛选
- 列显隐控制
- 批量操作
- 编辑/新增抽屉

```javascript
// 参考用法（TypeScript 需转 JS）
const { data, loading, columns, getData } = useNaivePaginatedTable({
  apiFn: () => getSubscriptions(),
  apiParams: {},
  columns: [
    { key: 'title', title: '名称', width: 200 },
  ],
})
```

### 场景：需要主题色切换

参考 `store/modules/theme/` 和 `packages/color/src/` 的实现，Naive UI 的 `NConfigProvider` 支持动态主题覆盖。

### 场景：需要多标签页

参考 `layouts/modules/global-tab/` 和 `store/modules/tab/` 的实现。

### 场景：需要 ECharts 图表

参考 `hooks/common/echarts.ts` 和 `views/home/modules/line-chart.vue`。