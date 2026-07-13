<template>
  <el-container class="app-container">
    <!-- 侧边栏 -->
    <el-aside width="220px" class="app-sidebar">
      <div class="logo">
        <h2>UniSub</h2>
        <p>统一媒体订阅聚合器</p>
      </div>
      <el-menu
        :default-active="activeRoute"
        router
        background-color="#304156"
        text-color="#bfcbd9"
        active-text-color="#409eff"
      >
        <el-menu-item index="/">
          <el-icon><DataAnalysis /></el-icon>
          <span>看板</span>
        </el-menu-item>
        <el-menu-item index="/search">
          <el-icon><Search /></el-icon>
          <span>搜索</span>
        </el-menu-item>
        <el-menu-item index="/subscriptions">
          <el-icon><Collection /></el-icon>
          <span>订阅管理</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon>
          <span>设置</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <!-- 主内容区 -->
    <el-container>
      <el-header class="app-header">
        <h3>{{ pageTitle }}</h3>
      </el-header>
      <el-main class="app-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { DataAnalysis, Search, Collection, Setting } from '@element-plus/icons-vue'

const route = useRoute()

const activeRoute = computed(() => route.path)
const pageTitle = computed(() => route.meta?.title || 'UniSub')
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html, body, #app {
  height: 100%;
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Hiragino Sans GB',
    'Microsoft YaHei', Arial, sans-serif;
}

.app-container {
  height: 100%;
}

.app-sidebar {
  background-color: #304156;
  overflow-y: auto;
}

.app-sidebar .logo {
  padding: 20px 16px;
  text-align: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.app-sidebar .logo h2 {
  color: #fff;
  font-size: 20px;
  margin-bottom: 4px;
}

.app-sidebar .logo p {
  color: #8899aa;
  font-size: 12px;
}

.app-sidebar .el-menu {
  border-right: none;
}

.app-header {
  background: #fff;
  border-bottom: 1px solid #e6e6e6;
  display: flex;
  align-items: center;
  padding: 0 24px;
  height: 56px;
}

.app-header h3 {
  font-size: 18px;
  color: #303133;
}

.app-main {
  background: #f0f2f5;
  min-height: calc(100vh - 56px);
  padding: 20px;
}
</style>
