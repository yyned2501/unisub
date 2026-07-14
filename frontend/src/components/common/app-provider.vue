<script setup>
import { defineComponent, createTextVNode } from 'vue'
import { useDialog, useLoadingBar, useMessage, useNotification } from 'naive-ui'

defineOptions({ name: 'AppProvider' })

const ContextHolder = defineComponent({
  name: 'ContextHolder',
  setup() {
    window.$message = useMessage()
    window.$dialog = useDialog()
    window.$notification = useNotification()
    window.$loadingBar = useLoadingBar()
    return () => createTextVNode()
  },
})
</script>

<template>
  <n-loading-bar-provider>
    <n-dialog-provider>
      <n-notification-provider>
        <n-message-provider>
          <ContextHolder />
          <slot />
        </n-message-provider>
      </n-notification-provider>
    </n-dialog-provider>
  </n-loading-bar-provider>
</template>
