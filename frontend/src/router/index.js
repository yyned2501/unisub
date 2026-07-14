import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
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
    path: '/settings/tasks',
    name: 'TaskSettings',
    component: () => import('../views/settings/TaskSettings.vue'),
    meta: { title: '定时任务' },
  },
  {
    path: '/settings',
    redirect: '/settings/platforms',
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.afterEach((to) => {
  const title = to.meta?.title
  if (title) {
    document.title = `${title} — UniSub`
  }
})

export async function setupRouter(app) {
  app.use(router)
  await router.isReady()
}

export default router
