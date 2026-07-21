# UniSub 前端规范（Claude Code 专属）

> 本文档是 Claude Code 修改 UniSub 前端代码时的**行为准则**。
> 所有前端修改必须完全遵守以下规范，否则视为不合格。
>
> **Soybean Admin 参考：** `SOYBEAN_REFERENCE.md` 列出了 `/home/hermes/projects/soybean-admin`
> 项目中可借鉴的模块。开发新功能时优先参考，避免重复造轮子。

---

## 1. 技术栈

| 项 | 规范 |
|:---|:---|
| 语言 | **TypeScript**（strict 模式） |
| 框架 | Vue 3 Composition API（`<script setup lang="ts">`） |
| UI 库 | **Naive UI** |
| 样式 | **UnoCSS**（原子化 CSS）+ RemixIcon |
| 状态管理 | Pinia |
| 路由 | Vue Router 4，懒加载 |
| HTTP | Axios，统一拦截器 + 响应解包（`service/request.ts`） |
| 工具库 | @vueuse/core（轮询等） |
| UI 语言 | 中文 |
| 类型门禁 | `npm run type-check`（vue-tsc --noEmit）必须零错误 |

## 2. TypeScript 约定（严格度分层）

采用「**领域层严格 + 视图层务实**」策略：

- **领域层严格**：`types/`、`service/api/`、`composables/`、`store/` 必须完整类型化，禁止 `any`。
- **视图层务实**：`.vue` 组件加 `lang="ts"`，props/emits 用泛型 `defineProps<{}>()`；遇到 Naive UI 复杂 props 类型摩擦可用 `as` 兜底，但**不得为类型正确而改业务逻辑**。

### 领域类型层 `src/types/`

- **镜像后端 Pydantic schemas**（`backend/app/schemas/`）与 router 响应，一一对应。
- 字段名保持 **snake_case** 与后端一致；后端 `datetime` → TS `string`（ISO）。
- 统一从 `@/types` 导入（`import type { Subscription } from '@/types'`）。
- **修改后端 schema 时必须同步更新此处**，否则 type-check 会暴露不一致。
- 通用类型：`Paginated<T>`、`ActionResponse`、`MediaType` 在 `common.ts`。

### 生成的文件（勿手改）

- `src/types/auto-imports.d.ts`、`src/types/components.d.ts` 由 unplugin 生成，已提交入库。
- 改了 auto-import 配置后跑一次 `npm run build` 重新生成。

## 3. 设计原则（DRY + 组件化 + 复用抽象层）

1. **DRY**：相同逻辑/UI 只写一次。发现重复立即抽成组件或 composable。
2. **组件化**：页面内容拆成小组件，每个组件只做一件事。
3. **解耦**：业务逻辑不进组件。API 调用、状态、工具分别归入 `service/api/`、`store/`、`utils/`、`composables/`，组件只管渲染和事件。
4. **优先复用通用层**：写新功能前先检查第 5 节的通用 composable，**禁止重新手写 loading 样板 / setInterval 轮询 / Set 展开 / window.$message 调用**。

## 4. 目录结构

```
frontend/src/
├── App.vue                # 入口布局（侧边栏 + 导航栏）
├── main.ts                # 入口
├── env.d.ts               # 全局类型声明（Window.$message 等）
├── plugins/               # 插件初始化
├── router/index.ts        # 路由定义（懒加载 + 守卫）
├── service/               # API 层（与后端 router 一一对应）
│   ├── request.ts         # Axios 实例 + 拦截器 + 解包的 http 客户端
│   └── api/*.ts           # 每个后端 router 一个文件
├── store/modules/         # Pinia 仓库
├── composables/           # 业务逻辑 + 通用 composable
│   ├── useAction.ts       # 通用：loading 包装
│   ├── usePolling.ts      # 通用：轮询
│   ├── useIdSet.ts        # 通用：行级 loading 集合
│   └── use*.ts            # 各页面业务逻辑
├── utils/
│   ├── message.ts         # msg 快捷方法 + confirmDialog
│   └── format.ts          # 格式化工具
├── types/                 # 领域类型（镜像后端 schemas）
├── components/            # 可复用组件
└── views/                 # 页面组件（每路由一个）
```

## 5. 通用抽象层（新功能必用）

| 模块 | 用途 | 替代了什么 |
|:---|:---|:---|
| `useAction(fn)` | 包装 async fn → `{ loading, run }` | 手写 `loading.value = true/finally false` |
| `usePolling(fn, ms, {immediate})` | 轮询，自动 onUnmounted 清理 | 手写 `setInterval` + `clearInterval` |
| `useIdSet()` | 行级 loading → `{ add, remove, has }` | `new Set([...set, id])` 展开样板 |
| `usePagedList(source, size)` | 前端分页 → `{ page, totalPages, pagedList, setPage, reset }` | 手写 page/slice/totalPages |
| `msg.success/error/warning/info` | 消息提示 | `window.$message?.xxx` |
| `confirmDialog({content})` | Promise 化确认框 | 手写 `window.$dialog` Promise |

**示例：**
```ts
const { loading, run: loadList } = useAction(async () => {
  list.value = await getSubscriptions()
})
const deleting = useIdSet()
async function remove(row: Subscription) {
  deleting.add(row.id)
  try { await deleteSubscription(row.id); msg.success('已删除') }
  finally { deleting.remove(row.id) }
}
usePolling(pollStatus, 3000, { immediate: true })
```

## 6. 分层职责

| 层 | 职责 | 禁止 |
|:---|:---|:---|
| `views/` | 页面骨架，调用 composable，渲染 | 写业务逻辑、直接调 API |
| `components/` | 纯 UI，props 进 / emit 出 | 调 store、调 API、调 msg |
| `composables/` | 业务逻辑、状态、调 API、调 msg | 操作 DOM |
| `service/api/` | 封装 http 请求，返回 `Promise<T>` | 处理 UI 状态、弹消息 |
| `store/` | 跨组件共享状态 | 存组件私有数据 |

## 7. API 层规范

```ts
// service/api/xxx.ts — 每个后端 router 对应一个文件
import http from '../request'
import type { PlatformConfig, PlatformConfigUpdate } from '@/types'

export function getPlatforms() {
  return http.get<PlatformConfig[]>('/platforms')
}
export function updatePlatform(id: string, data: PlatformConfigUpdate) {
  return http.put<PlatformConfig>(`/platforms/${id}`, data)
}
```

- **`http` 已解包响应**：`http.get<T>()` 直接返回 `Promise<T>`（业务数据），**不是** AxiosResponse。
- 调用方直接 `const data = await getPlatforms()`，**不要** `const { data } = ...`。
- 每个文件导出命名函数，camelCase，不处理 UI 状态。
- 路径相对 `/api` 前缀（已在 request.ts 配置 baseURL）。

## 8. 编码约定

- 使用 **Naive UI** 组件，保持风格统一。
- 样式优先 **UnoCSS 原子化 class**，复杂样式用 `<style scoped>`。
- 图标用 **RemixIcon**（`<i class="ri-xxx-line">`），不引入其他图标库。
- 路由异步懒加载（`() => import(...)`），hash 模式，每路由 `meta.title`（中文）。
- 状态走 Pinia，不在组件内直接改共享状态。
- 暗色模式经 `themeStore` 统一管理。
- 文件命名：Vue 组件 PascalCase（`DashboardView.vue`），TS 模块 camelCase/kebab-case（`request.ts`、`use-action.ts` 风格二选一，现状 camelCase）。
- 错误处理：API 错误已在拦截器统一弹消息；业务层需定制提示时用 `msg`，catch 里取 `detail` 用 `(e as AxiosError<{detail?: string}>)?.response?.data?.detail`。

## 9. 验证（提交前必做）

```bash
cd frontend
npm run build        # 构建通过
npm run type-check   # 类型零错误
npm run lint         # eslint 零错误（自动 --fix）
```

- 代码风格由 **Prettier** 统一（`.prettierrc`）：无分号、单引号、printWidth 120。改完可跑 `npm run format`。
- ESLint（flat config，`eslint.config.js`）：TS + Vue 推荐规则；视图层允许 `any`；模板排版规则交给 Prettier。
- 改了前端 → `npm run build && npm run type-check`。
- 改了后端 → `sudo systemctl restart unisub-backend`，`sleep 3 && curl http://localhost:8002/api/platforms`。
