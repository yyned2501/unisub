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

<style scoped>
.arch {
  --c1: #2563eb;
  --c1-soft: rgba(37, 99, 235, 0.06);
  --c1-line: rgba(37, 99, 235, 0.3);
  --c2: #b45309;
  --c2-soft: rgba(180, 83, 9, 0.06);
  --c2-line: rgba(180, 83, 9, 0.3);
  --c3: #7c3aed;
  --c3-soft: rgba(124, 58, 237, 0.06);
  --c3-line: rgba(124, 58, 237, 0.3);
  --c4: #dc2626;
  --c4-soft: rgba(220, 38, 38, 0.06);
  --c4-line: rgba(220, 38, 38, 0.3);
  --panel: #fff;
  --panel-border: rgba(0, 0, 0, 0.09);
  --dot: rgba(0, 0, 0, 0.08);
  --muted: rgba(0, 0, 0, 0.48);
  --code-bg: rgba(0, 0, 0, 0.045);
  --code-border: rgba(0, 0, 0, 0.08);
  --mono: ui-monospace, 'SF Mono', 'Cascadia Code', Menlo, Consolas, monospace;
}

:global(html.dark) .arch {
  --c1: #4a8fe8;
  --c1-soft: rgba(74, 143, 232, 0.09);
  --c1-line: rgba(74, 143, 232, 0.35);
  --c2: #c4880a;
  --c2-soft: rgba(196, 136, 10, 0.09);
  --c2-line: rgba(196, 136, 10, 0.35);
  --c3: #9c5bc4;
  --c3-soft: rgba(156, 91, 196, 0.09);
  --c3-line: rgba(156, 91, 196, 0.35);
  --c4: #c0503a;
  --c4-soft: rgba(192, 80, 58, 0.09);
  --c4-line: rgba(192, 80, 58, 0.35);
  --panel: rgba(255, 255, 255, 0.035);
  --panel-border: rgba(255, 255, 255, 0.1);
  --dot: rgba(255, 255, 255, 0.07);
  --muted: rgba(255, 255, 255, 0.48);
  --code-bg: rgba(255, 255, 255, 0.06);
  --code-border: rgba(255, 255, 255, 0.1);
}

/* 入场动画 */
.reveal {
  animation: fade-up 0.5s ease backwards;
}
@keyframes fade-up {
  from {
    opacity: 0;
    transform: translateY(16px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 头部 */
.arch-logo {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: linear-gradient(135deg, #3b82f6, #2563eb);
  color: #fff;
  font-size: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.arch-title {
  font-size: 22px;
  font-weight: 800;
  letter-spacing: 0.5px;
}
.arch-sub {
  font-size: 13px;
  color: var(--muted);
}

/* 代码片段 */
.arch code {
  font-family: var(--mono);
  font-size: 0.86em;
  background: var(--code-bg);
  border: 1px solid var(--code-border);
  padding: 1px 6px;
  border-radius: 4px;
}

/* 定时器徽章 */
.timer-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: var(--mono);
  font-size: 11.5px;
  font-weight: 600;
  padding: 5px 10px;
  border-radius: 6px;
  border: 1px solid;
}
.tc-1 {
  color: var(--c1);
  border-color: var(--c1-line);
  background: var(--c1-soft);
}
.tc-2 {
  color: var(--c2);
  border-color: var(--c2-line);
  background: var(--c2-soft);
}
.tc-3 {
  color: var(--c3);
  border-color: var(--c3-line);
  background: var(--c3-soft);
}
.tc-4 {
  color: var(--c4);
  border-color: var(--c4-line);
  background: var(--c4-soft);
}

/* 四条线卡片 */
.line-card {
  background: var(--panel);
  border: 1px solid var(--panel-border);
  border-left-width: 3px;
  border-radius: 10px;
  padding: 18px 20px;
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease;
}
.line-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.14);
}
.line-1 {
  border-left-color: var(--c1);
  --lc: var(--c1);
  --lc-soft: var(--c1-soft);
  --lc-line: var(--c1-line);
}
.line-2 {
  border-left-color: var(--c2);
  --lc: var(--c2);
  --lc-soft: var(--c2-soft);
  --lc-line: var(--c2-line);
}
.line-3 {
  border-left-color: var(--c3);
  --lc: var(--c3);
  --lc-soft: var(--c3-soft);
  --lc-line: var(--c3-line);
}
.line-4 {
  border-left-color: var(--c4);
  --lc: var(--c4);
  --lc-soft: var(--c4-soft);
  --lc-line: var(--c4-line);
}
.line-badge {
  font-size: 11px;
  font-weight: 800;
  color: #fff;
  background: var(--lc);
  padding: 3px 9px;
  border-radius: 5px;
  letter-spacing: 1px;
  flex-shrink: 0;
  margin-top: 2px;
}
.line-title {
  font-size: 15.5px;
  font-weight: 700;
}
.line-sub {
  font-size: 12px;
  color: var(--muted);
  margin-top: 2px;
}
.line-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--muted);
  background: var(--code-bg);
  border: 1px solid var(--code-border);
  padding: 4px 10px;
  border-radius: 6px;
  margin: 12px 0;
}
.line-steps {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.line-steps li {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}
.step-dot {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--lc-soft);
  color: var(--lc);
  border: 1px solid var(--lc-line);
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 1px;
}
.step-text {
  font-size: 13px;
  line-height: 1.65;
}
.step-tag {
  font-style: normal;
  font-size: 10.5px;
  font-weight: 700;
  color: var(--lc);
  background: var(--lc-soft);
  border: 1px solid var(--lc-line);
  padding: 1px 6px;
  border-radius: 4px;
  margin-right: 6px;
  vertical-align: 1px;
}
.line-steps code {
  margin-left: 4px;
  white-space: nowrap;
}

/* 面板通用 */
.panel-title {
  font-size: 15px;
  font-weight: 800;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  letter-spacing: 0.5px;
}
.panel-title i {
  font-size: 17px;
}
.pt-flow i {
  color: var(--c1);
}
.pt-notes i {
  color: var(--c2);
}
.pt-db i {
  color: var(--c3);
}

/* 流程图面板 */
.flow-panel {
  background-color: var(--panel);
  background-image: radial-gradient(var(--dot) 1px, transparent 1.4px);
  background-size: 22px 22px;
  border: 1px solid var(--panel-border);
  border-radius: 12px;
  padding: 22px 24px;
}
.flow-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 5px 0;
}
.node {
  padding: 7px 14px;
  border-radius: 8px;
  font-size: 12.5px;
  font-weight: 600;
  white-space: nowrap;
  transition: transform 0.15s ease;
}
.node:hover {
  transform: translateY(-2px);
}
.node small {
  font-size: 10px;
  opacity: 0.75;
  margin-left: 5px;
  font-weight: 500;
}
.node-ext {
  border: 1px dashed var(--muted);
  color: var(--muted);
  font-weight: 500;
}
.node-solid {
  border-style: solid;
}
.node-db {
  border: 1px solid var(--panel-border);
  background: var(--code-bg);
  border-radius: 4px 4px 10px 10px;
  font-family: var(--mono);
  font-size: 12px;
}
.node-p1 {
  color: var(--c1);
  background: var(--c1-soft);
  border: 1px solid var(--c1-line);
}
.node-p2 {
  color: var(--c2);
  background: var(--c2-soft);
  border: 1px solid var(--c2-line);
}
.node-p3 {
  color: var(--c3);
  background: var(--c3-soft);
  border: 1px solid var(--c3-line);
}
.node-p4 {
  color: var(--c4);
  background: var(--c4-soft);
  border: 1px solid var(--c4-line);
}
.arrow {
  color: var(--muted);
  font-size: 15px;
  user-select: none;
}
.flow-connector {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: var(--muted);
  font-size: 12px;
  padding: 9px 0;
}
.flow-divider {
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--muted);
  font-size: 11.5px;
  margin: 12px 0 8px;
}
.flow-divider::before,
.flow-divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--panel-border);
}

/* 关键设计 */
.key-notes {
  background: var(--panel);
  border: 1px solid var(--panel-border);
  border-left: 3px solid var(--c2);
  border-radius: 10px;
  padding: 20px 24px;
}
.notes-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.notes-list li {
  font-size: 13px;
  line-height: 1.9;
}
.notes-list em {
  font-style: normal;
  font-weight: 700;
}
.tag {
  display: inline-block;
  font-size: 10.5px;
  font-weight: 800;
  padding: 1px 7px;
  border-radius: 4px;
  margin-right: 7px;
  letter-spacing: 0.5px;
  vertical-align: 1px;
}
.tag-1 {
  color: var(--c1);
  background: var(--c1-soft);
  border: 1px solid var(--c1-line);
}
.tag-2 {
  color: var(--c2);
  background: var(--c2-soft);
  border: 1px solid var(--c2-line);
}
.tag-3 {
  color: var(--c3);
  background: var(--c3-soft);
  border: 1px solid var(--c3-line);
}
.tag-4 {
  color: var(--c4);
  background: var(--c4-soft);
  border: 1px solid var(--c4-line);
}

/* 数据表 */
.db-card {
  background: var(--panel);
  border: 1px solid var(--panel-border);
  border-radius: 10px;
  padding: 14px 16px;
  text-align: center;
  transition:
    transform 0.2s ease,
    border-color 0.2s ease;
}
.db-card:hover {
  transform: translateY(-2px);
  border-color: var(--c1-line);
}
.db-name {
  font-family: var(--mono);
  font-size: 13px;
  font-weight: 700;
  color: var(--c1);
}
.db-desc {
  font-size: 11.5px;
  color: var(--muted);
  margin-top: 5px;
}

@media (prefers-reduced-motion: reduce) {
  .reveal {
    animation: none;
  }
  .line-card:hover,
  .node:hover,
  .db-card:hover {
    transform: none;
  }
}
</style>
