<script setup>
import { useCd2Settings } from '@/composables/useCd2Settings'

defineOptions({ name: 'Cd2Settings' })

const {
  form,
  loading,
  saving,
  testing,
  saveConfig,
  testConnection,
} = useCd2Settings()
</script>

<template>
  <div>
    <div class="mb-4">
      <h2 class="text-lg font-bold">CloudDrive2 设置</h2>
      <p class="text-sm opacity-55 mt-1">配置 gRPC API 连接及无效媒体目录的移动目标位置。</p>
    </div>

    <n-spin :show="loading">
      <n-card title="连接设置" size="small" class="max-w-2xl">
        <template #header-extra>
          <n-switch v-model:value="form.enabled" size="small">
            <template #checked>已启用</template>
            <template #unchecked>已停用</template>
          </n-switch>
        </template>

        <n-form label-placement="top" :model="form">
          <n-form-item label="URL">
            <n-input
              v-model:value="form.base_url"
              placeholder="例如：192.168.31.10:19798"
            />
            <template #feedback>CloudDrive2 gRPC 服务地址，支持填写 host:port 或 http://host:port。</template>
          </n-form-item>

          <n-form-item label="API Key">
            <n-input
              v-model:value="form.api_key"
              type="password"
              show-password-on="click"
              placeholder="CloudDrive2 API Token"
            />
            <template #feedback>使用带文件读取和移动权限的 API Token。</template>
          </n-form-item>

          <n-form-item label="移动到的位置">
            <n-input
              v-model:value="form.target_path"
              placeholder="/115open/待整理/转存/"
            />
            <template #feedback>检测到错误 TMDB ID 后，媒体文件夹将移动到此 CD2 目录。</template>
          </n-form-item>

          <n-divider />

          <h3 class="text-sm font-medium mb-2">路径映射（可选）</h3>
          <p class="text-xs opacity-55 mb-3">将 Emby 中的媒体路径前缀替换为 CD2 中的对应路径，用于定位和移动文件。</p>

          <n-form-item label="Emby 路径前缀">
            <n-input
              v-model:value="form.path_prefix"
              placeholder="/media/Symedia/MoviePilot"
            />
            <template #feedback>Emby 中媒体路径的前缀部分。</template>
          </n-form-item>

          <n-form-item label="替换为 CD2 路径">
            <n-input
              v-model:value="form.path_replacement"
              placeholder="/115open/已整理"
            />
            <template #feedback>替换为 CD2 文件系统中的对应路径前缀。</template>
          </n-form-item>
        </n-form>

        <div class="flex gap-2 pt-4" style="border-top: 1px solid var(--n-border-color)">
          <n-button type="primary" :loading="saving" @click="saveConfig">
            <template #icon><i class="ri-save-line"></i></template>
            保存
          </n-button>
          <n-button secondary :loading="testing" :disabled="saving" @click="testConnection">
            <template #icon><i class="ri-plug-line"></i></template>
            测试连接
          </n-button>
        </div>
      </n-card>
    </n-spin>
  </div>
</template>
