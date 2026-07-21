import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { setupAssets } from './plugins'
import { setupRouter } from './router'
import App from './App.vue'

async function setupApp() {
  setupAssets()

  const app = createApp(App)

  app.use(createPinia())

  await setupRouter(app)

  app.mount('#app')
}

setupApp()
