import { defineConfig } from 'vite'
import type { Plugin } from 'vite'
import { URL, fileURLToPath } from 'node:url'
import vue from '@vitejs/plugin-vue'
import unoCss from 'unocss/vite'
import autoImport from 'unplugin-auto-import/vite'
import components from 'unplugin-vue-components/vite'
import { NaiveUiResolver } from 'unplugin-vue-components/resolvers'

/**
 * remixicon 的 @font-face 同时声明 eot/woff2/woff/ttf/svg，Vite 会把五种格式
 * 全部拷进产物（约 4.3MB）。现代浏览器只命中列表首位的 woff2，其余四种是
 * IE9/iOS4 时代的死重，直接从 bundle 里剔除。
 */
const woff2OnlyFonts: Plugin = {
  name: 'unisub-woff2-only-fonts',
  apply: 'build',
  generateBundle(_options, bundle) {
    for (const fileName of Object.keys(bundle)) {
      if (/remixicon[^/]*\.(eot|ttf|woff|svg)$/i.test(fileName)) {
        delete bundle[fileName]
      }
    }
  },
}

export default defineConfig({
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    chunkSizeWarningLimit: 600,
    reportCompressedSize: true,
    rollupOptions: {
      output: {
        // 只拆分真正稳定且体积较大的运行时库；
        // naive-ui 已由 unplugin-vue-components 按需解析，不要强制全量打包
        manualChunks: {
          vue: ['vue', 'vue-router', 'pinia'],
          http: ['axios'],
          tools: ['@vueuse/core'],
        },
      },
    },
  },
  plugins: [
    vue(),
    unoCss(),
    woff2OnlyFonts,
    autoImport({
      imports: [
        'vue',
        'vue-router',
        {
          'naive-ui': ['useDialog', 'useMessage', 'useNotification', 'useLoadingBar'],
        },
      ],
      dts: 'src/types/auto-imports.d.ts',
    }),
    components({
      resolvers: [NaiveUiResolver()],
      dts: 'src/types/components.d.ts',
    }),
  ],
  server: {
    port: 9527,
    proxy: {
      '/api': {
        target: 'http://localhost:8002',
        changeOrigin: true,
      },
    },
  },
})
