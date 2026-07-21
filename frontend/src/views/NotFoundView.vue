<script setup lang="ts">
import { useRouter } from 'vue-router'

defineOptions({ name: 'NotFoundView' })

const router = useRouter()
</script>

<template>
  <div class="flex flex-col items-center justify-center py-30">
    <div class="text-7xl font-bold opacity-20 mb-2">404</div>
    <div class="text-sm opacity-50 mb-6">页面不存在或已被移除</div>
    <n-button type="primary" size="small" @click="router.push('/')">
      <template #icon><i class="ri-home-line"></i></template>
      回到看板
    </n-button>
  </div>
</template>
