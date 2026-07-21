import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '@/store/modules/auth'
import type { RouteRecordRaw } from 'vue-router'
import type { App } from 'vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/LoginView.vue'),
    meta: { title: '登录', noAuth: true },
  },
  {
    path: '/',
    name: 'Dashboard',
    component: () => import('../views/DashboardView.vue'),
    meta: { title: '看板' },
  },
  {
    path: '/search',
    name: 'Search',
    component: () => import('../views/SearchView.vue'),
    meta: { title: '搜索' },
  },
  {
    path: '/subscriptions',
    name: 'Subscriptions',
    component: () => import('../views/SubscriptionsView.vue'),
    meta: { title: '订阅管理' },
  },
  {
    path: '/settings/platforms',
    name: 'PlatformSettings',
    component: () => import('../views/settings/PlatformSettings.vue'),
    meta: { title: '平台配置' },
  },
  {
    path: '/settings/cd2',
    name: 'Cd2Settings',
    component: () => import('../views/settings/Cd2Settings.vue'),
    meta: { title: 'CloudDrive2 设置' },
  },
  {
    path: '/settings/tasks',
    name: 'TaskSettings',
    component: () => import('../views/settings/TaskSettings.vue'),
    meta: { title: '定时任务' },
  },
  {
    path: '/settings/account',
    name: 'AccountSettings',
    component: () => import('../views/settings/AccountSettings.vue'),
    meta: { title: '账号设置' },
  },
  {
    path: '/settings/auto-subscribe',
    name: 'AutoSubscribe',
    component: () => import('../views/settings/AutoSubscribeSettings.vue'),
    meta: { title: '自动订阅' },
  },
  {
    path: '/settings/logs',
    name: 'LogViewer',
    component: () => import('../views/settings/LogViewer.vue'),
    meta: { title: '日志查看' },
  },
  {
    path: '/emby',
    name: 'EmbyAnalysis',
    component: () => import('../views/settings/EmbyAnalysis.vue'),
    meta: { title: '媒体库' },
  },
  {
    path: '/emby/tmdb-404',
    name: 'Tmdb404',
    component: () => import('../views/emby/Tmdb404View.vue'),
    meta: { title: '无 TMDB 媒体' },
  },
  {
    path: '/settings',
    redirect: '/settings/platforms',
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('../views/NotFoundView.vue'),
    meta: { title: '页面不存在', noAuth: true },
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

// 路由守卫 — 未登录跳转到登录页
router.beforeEach((to, from, next) => {
  if (to.meta?.noAuth) {
    next()
    return
  }
  const auth = useAuthStore()
  if (!auth.checkAuth()) {
    next('/login')
    return
  }
  next()
})

router.afterEach((to) => {
  const title = to.meta?.title
  if (title) {
    document.title = `${title} — UniSub`
  }
})

export async function setupRouter(app: App) {
  app.use(router)
  await router.isReady()
}

export default router
