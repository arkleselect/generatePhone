<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, loadDefects } from './api'
import type { Asset, Config, Detail } from './types'
import Library from './components/Library.vue'
import BatchCreate from './components/BatchCreate.vue'
import BatchHistory from './components/BatchHistory.vue'
import Review from './components/Review.vue'
import ConfigDialog from './components/ConfigDialog.vue'
// Shared assets reload after mutations; navigation preserves no hidden generation side effects.
const page = ref('library'), assets = ref<Asset[]>([]), config = ref<Config>(), showConfig = ref(false)
const activeDraft = ref<Detail>(), refreshKey = ref(0), loading = ref(false)
const pages = [{ id: 'library', title: '参考图与底图库' }, { id: 'create', title: '创建批量任务' }, { id: 'history', title: '任务与历史' }, { id: 'review', title: '审核与导出' }]
async function refresh() {
  loading.value = true
  try { [assets.value, config.value] = await Promise.all([api<Asset[]>('/assets'), api<Config>('/config'), loadDefects()]) }
  finally { loading.value = false }
}
function openDraft(detail: Detail) { activeDraft.value = detail; page.value = 'history'; refreshKey.value++ }
onMounted(() => { void refresh().catch(() => undefined) })
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <nav aria-label="主导航"><button v-for="item in pages" :key="item.id" :class="{ active: page === item.id }" @click="page = item.id">{{ item.title }}</button></nav>
      <div class="sidebar-bottom"><button class="config-button" @click="showConfig = true">账号生图设置</button></div>
    </aside>
    <div class="main-shell">
      <header class="topbar"><span>{{ pages.find(item => item.id === page)?.title }}</span><div><el-button text @click="showConfig = true">账号设置</el-button><el-button text :loading="loading" @click="refresh">刷新数据</el-button></div></header>
      <main>
        <Library v-if="page === 'library'" :assets="assets" @refresh="refresh" @create="page = 'create'" />
        <BatchCreate v-else-if="page === 'create'" :assets="assets"  @created="openDraft" />
        <BatchHistory v-else-if="page === 'history'" :key="refreshKey" :initial="activeDraft" :assets="assets" @refresh="refresh" @draft="openDraft" />
        <Review v-else :assets="assets" @refresh="refresh" @draft="openDraft" />
      </main>

    </div>
    <ConfigDialog v-model="showConfig" :config="config" @saved="refresh" />
  </div>
</template>
