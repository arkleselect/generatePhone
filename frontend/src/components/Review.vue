<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api, defectNames, imageUrl, shortId, statusText } from '../api'
import type { Asset, Detail, Task } from '../types'
import ReviewDialog from './ReviewDialog.vue'
const props = defineProps<{ assets: Asset[] }>(), emit = defineEmits<{ refresh: []; draft: [Detail] }>()
const review = ref('APPROVED'), pose = ref(''), defect = ref(''), reviewing = ref<Asset>(), exporting = ref(false)
const expected = ref<Record<string,string>>({})
const results = computed(() => props.assets.filter(a => a.role === 'RESULT').filter(a => review.value === 'ALL' || a.review === review.value).filter(a => !pose.value || a.parentPoseId === pose.value).filter(a => !defect.value || expected.value[a.taskId || ''] === defect.value))
// Load intended labels independently from human-confirmed labels for the defect filter.
async function loadExpected() { for (const t of await api<Task[]>('/tasks')) expected.value[t.id] = t.params.defect?.type || '' }
void loadExpected().catch(() => undefined)
async function regenerate(asset: Asset) { if (asset.taskId) emit('draft', await api<Detail>(`/tasks/${asset.taskId}/regenerate`, 'POST')) }
async function download() {
  exporting.value = true
  try {
    const params = new URLSearchParams({ review: review.value, pose: pose.value, defect: defect.value })
    const response = await fetch(`/api/export?${params}`)
    if (!response.ok) { const error = await response.json(); throw new Error(error.message) }
    const url = URL.createObjectURL(await response.blob()), link = document.createElement('a'); link.href = url; link.download = 'hamlab-dataset.zip'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '导出失败') } finally { exporting.value = false }
}
</script>
<template>
  <section class="page-heading"><div><h1>结果审核与导出</h1><p>并排检查来源与结果，独立记录人工标签和产品质量判定。</p></div><el-button type="primary" size="large" :loading="exporting" @click="download">↓ 导出 ZIP 数据集</el-button></section>
  <div class="panel filter-bar"><el-select v-model="review" aria-label="审核状态"><el-option label="审核通过（默认导出）" value="APPROVED" /><el-option label="待审核" value="PENDING" /><el-option label="不通过" value="REJECTED" /><el-option label="全部状态（含未审核）" value="ALL" /></el-select><el-select v-model="pose" clearable placeholder="全部底图"><el-option v-for="a in assets.filter(a => a.role === 'POSE')" :key="a.id" :label="shortId(a.id)" :value="a.id" /></el-select><el-select v-model="defect" clearable placeholder="全部预期缺陷"><el-option v-for="(name,key) in defectNames" :key="key" :label="name" :value="key" /></el-select><span class="muted">{{ results.length }} 张结果</span></div>
  <div class="export-note">默认只导出审核通过的样本，测试图始终排除。ZIP 包含原始生成图片、JSONL 标签清单和参数快照；不编造检测框或分割标注。</div>
  <div v-if="!results.length" class="empty-state"><div class="empty-frame"><span>✓</span></div><h2>暂无符合条件的结果</h2><p>若已有生成结果，将审核筛选切换为“待审核”。</p></div>
  <div class="image-grid"><article v-for="a in results" :key="a.id" class="image-card"><div class="image-preview"><el-image :src="imageUrl(a.id,true)" :preview-src-list="[imageUrl(a.id)]" fit="contain" preview-teleported /><span class="image-source" :class="{test:a.sourceType === 'TEST'}">{{ a.sourceType === 'TEST' ? '测试 / 不导出' : 'AI 合成数据' }}</span></div><div class="image-info"><div class="card-title"><b>{{ shortId(a.id) }}</b><el-tag :type="a.review === 'APPROVED' ? 'success' : a.review === 'REJECTED' ? 'danger' : 'info'" size="small">{{ a.review === 'PENDING' ? '待审核' : statusText[a.review] }}</el-tag></div><p>人工标签 {{ a.label || '尚未确认' }} · {{ a.quality || '—' }}</p><p class="muted">来源 {{ shortId(a.rootSourceId) }}</p><div class="card-actions"><el-button size="small" @click="reviewing = a">对照审核</el-button><el-button size="small" @click="regenerate(a)">从同一底图再生成</el-button></div></div></article></div>
  <ReviewDialog v-if="reviewing" :asset="reviewing" :assets="assets" @close="reviewing = undefined" @saved="reviewing = undefined; emit('refresh')" />
</template>
