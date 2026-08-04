<script setup lang="ts">
defineOptions({ name: 'ArchitectureView' })

interface Step {
  tag?: string
  text: string
  code?: string
}

interface ArchLine {
  id: number
  badge: string
  title: string
  subtitle: string
  trigger: string
  steps: Step[]
}

const lines: ArchLine[] = [
  {
    id: 1,
    badge: '线 1',
    title: 'Emby 扫描 + TMDB 刷新',
    subtitle: '本地媒体库 → 元数据同步',
    trigger: '轻量 10min / 全量 60min · auto_sync_enabled',
    steps: [
      { text: '访问 Emby API，同步媒体列表', code: 'emby_cache' },
      { text: '对缓存条目查询 TMDB API', code: 'tmdb_cache' },
      { tag: '仅全量', text: '触发线 3 的 NextFind 同步' },
    ],
  },
  {
    id: 2,
    badge: '线 2',
    title: '自动订阅 · 发现新内容',
    subtitle: '豆瓣 / Mikan / 猫眼 榜单',
    trigger: 'Cron 表达式 · schedule_cron',
    steps: [
      { text: '并发抓取各榜单源' },
      { text: '全局 + 每源过滤（类型 / 年份 / 评分）' },
      { text: 'TMDB 搜索（优先）/ NextFind 兜底' },
      { text: '标题相似度校验 → 查本地 DB 去重' },
      { text: '新条目 → 调 NF 创建订阅', code: 'subscriptions' },
    ],
  },
  {
    id: 3,
    badge: '线 3',
    title: 'NextFind 双向同步',
    subtitle: '本地 ⇄ NF 状态一致',
    trigger: '嵌入全量扫描 Step 3 · 可手动触发',
    steps: [
      { text: '清理 NF 无元数据异常订阅' },
      { text: 'NF → 本地：更新状态 / 缺集数，多余则取消' },
      { text: '本地 → NF：推送未订阅条目' },
      { text: '电影完成状态（is_in_library）' },
      { text: '剧集完成状态（emby 集数 vs tmdb 集数）' },
      { text: '清理 NF 无效 cancelled 条目' },
    ],
  },
]

const dbTables = [
  { name: 'emby_cache', desc: 'Emby 本地库集数快照' },
  { name: 'tmdb_cache', desc: 'TMDB 总集数 / 已播集数' },
  { name: 'subscriptions', desc: '订阅记录 + NF 状态' },
  { name: 'activity_logs', desc: '操作日志' },
]
</script>

<template>
  <div class="arch">
    <!-- 头部 -->
    <header class="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <div class="flex items-center gap-3">
          <span class="arch-logo"><i class="ri-flow-chart"></i></span>
          <h1 class="arch-title">系统架构 · 定时任务数据流</h1>
        </div>
        <p class="arch-sub mt-2.5">
          <code>scheduler._loop</code> 统一驱动 3 条定时线 · 全量扫描内嵌 NextFind 同步
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <span class="timer-chip tc-1"><i class="ri-refresh-line"></i>10min / 60min</span>
        <span class="timer-chip tc-2"><i class="ri-calendar-2-line"></i>cron 触发</span>
        <span class="timer-chip tc-3"><i class="ri-exchange-2-line"></i>随全量扫描</span>
        <span class="timer-chip tc-4"><i class="ri-download-cloud-2-line"></i>默认 30s</span>
      </div>
    </header>

    <!-- 四条线卡片 -->
    <section class="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
      <article
        v-for="(line, i) in lines"
        :key="line.id"
        class="line-card reveal"
        :class="`line-${line.id}`"
        :style="{ animationDelay: `${i * 90}ms` }"
      >
        <div class="flex items-start gap-3">
          <span class="line-badge">{{ line.badge }}</span>
          <div class="min-w-0">
            <h2 class="line-title">{{ line.title }}</h2>
            <p class="line-sub">{{ line.subtitle }}</p>
          </div>
        </div>
        <div class="line-trigger"><i class="ri-timer-flash-line"></i>{{ line.trigger }}</div>
        <ol class="line-steps">
          <li v-for="(step, j) in line.steps" :key="j">
            <span class="step-dot">{{ j + 1 }}</span>
            <span class="step-text">
              <em v-if="step.tag" class="step-tag">{{ step.tag }}</em>
              {{ step.text }}
              <code v-if="step.code">{{ step.code }}</code>
            </span>
          </li>
        </ol>
      </article>
    </section>

    <!-- 调度关系总览 -->
    <section class="flow-panel reveal mb-6" :style="{ animationDelay: '380ms' }">
      <h2 class="panel-title pt-flow"><i class="ri-route-line"></i>调度关系总览</h2>

      <div class="flow">
        <div class="flow-row">
          <span class="node node-ext">Emby Server</span>
          <span class="arrow">→</span>
          <span class="node node-p1">线1 sync_cache</span>
          <span class="arrow">→</span>
          <span class="node node-db">emby_cache</span>
          <span class="arrow">→</span>
          <span class="node node-ext">TMDB API</span>
          <span class="arrow">→</span>
          <span class="node node-db">tmdb_cache</span>
        </div>

        <div class="flow-connector"><i class="ri-arrow-down-line"></i>全量扫描完成后触发</div>

        <div class="flow-row">
          <span class="node node-db">subscriptions</span>
          <span class="arrow">⇄</span>
          <span class="node node-p3">线3 sync_subscriptions</span>
          <span class="arrow">⇄</span>
          <span class="node node-ext">NextFind API</span>
        </div>

        <div class="flow-divider">独立定时线</div>

        <div class="flow-row">
          <span class="node node-ext">豆瓣 / Mikan / 猫眼</span>
          <span class="arrow">→</span>
          <span class="node node-p2">线2 auto_subscribe</span>
          <span class="arrow">→</span>
          <span class="node node-ext">TMDB / NF 搜索</span>
          <span class="arrow">→</span>
          <span class="node node-db">subscriptions</span>
        </div>
      </div>
    </section>

    <!-- 关键设计 -->
    <section class="key-notes reveal mb-6" :style="{ animationDelay: '480ms' }">
      <h2 class="panel-title pt-notes"><i class="ri-lightbulb-flash-line"></i>关键设计</h2>
      <ul class="notes-list">
        <li>
          <span class="tag tag-3">线3</span>不是独立定时器 — 嵌入<span class="tag tag-1">线1</span>全量扫描的 Step
          3（每 60min 随全量跑一次），也可通过 API 手动触发
        </li>
        <li>
          <span class="tag tag-2">线2</span>目的是「发现新内容」— 只判断 已订阅? / 已入库?，<strong>不判断缺集</strong>
        </li>
        <li><span class="tag tag-1">线1</span>轻量刷新只补<em>缺失</em>的 TMDB 数据；全量才刷新所有条目</li>
      </ul>
    </section>

    <!-- 核心数据表 -->
    <section class="reveal" :style="{ animationDelay: '560ms' }">
      <h2 class="panel-title pt-db"><i class="ri-database-2-line"></i>核心数据表</h2>
      <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div v-for="t in dbTables" :key="t.name" class="db-card">
          <div class="db-name">{{ t.name }}</div>
          <div class="db-desc">{{ t.desc }}</div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped src="./architecture.css"></style>
