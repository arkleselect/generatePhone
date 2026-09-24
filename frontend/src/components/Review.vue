<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, defectNames, imageUrl, shortId, statusText } from '../api'
import type { Asset, Batch, Detail, Task } from '../types'
import ReviewDialog from './ReviewDialog.vue'
const props = defineProps<{ assets: Asset[] }>(), emit = defineEmits<{ refresh: []; draft: [Detail] }>()
const review = ref('ALL'), defect = ref(''), reviewing = ref<Asset>(), exporting = ref(false), busy = ref(false)
const batches = ref<Batch[]>([]), tasks = ref<Task[]>([]), batchId = ref(''), selected = ref<string[]>([])
const taskMap = computed(() => new Map(tasks.value.map(t => [t.id, t])))
const generated = computed(() => props.assets.filter(a => a.taskId && taskMap.value.has(a.taskId)))
const reviewBatches = computed(() => batches.value.filter(b => generated.value.some(a => taskMap.value.get(a.taskId!)?.batchId === b.id)))
const currentBatch = computed(() => reviewBatches.value.find(b => b.id === batchId.value))
const batchAssets = computed(() => generated.value.filter(a => taskMap.value.get(a.taskId!)?.batchId === batchId.value))
const results = computed(() => batchAssets.value.filter(a => review.value === 'ALL' || a.review === review.value).filter(a => !defect.value || taskMap.value.get(a.taskId!)?.params.defect?.type === defect.value))
const counts = computed(() => ({ all: batchAssets.value.length, pending: batchAssets.value.filter(a => a.review === 'PENDING').length, approved: batchAssets.value.filter(a => a.review === 'APPROVED').length, rejected: batchAssets.value.filter(a => a.review === 'REJECTED').length }))
watch(() => props.assets, async () => {
  try {
    const [b, t] = await Promise.all([api<Batch[]>('/batches'), api<Task[]>('/tasks')])
    batches.value = b; tasks.value = t
    if (!reviewBatches.value.some(b => b.id === batchId.value)) batchId.value = reviewBatches.value[0]?.id || ''
    selected.value = selected.value.filter(id => results.value.some(a => a.id === id))
  } catch { /* Shared transport displays failures. */ }
}, { immediate: true })
watch([batchId, review, defect], () => { selected.value = [] })
watch(batchId, () => { defect.value = ''; review.value = 'ALL' })
async function regenerate(asset: Asset) { if (asset.taskId) emit('draft', await api<Detail>(`/tasks/${asset.taskId}/regenerate`, 'POST')) }
async function batchReview(status: 'APPROVED' | 'REJECTED') {
  const id = batchId.value
  const ids = status === 'APPROVED' ? batchAssets.value.map(a => a.id) : [...selected.value]
  if (!id || !ids.length) return
  let reason = ''
  try {
    if (status === 'APPROVED') {
      await ElMessageBox.confirm(`确认本批次当前已生成的全部 ${ids.length} 张图片均符合各自任务要求？包括筛选隐藏和之前不通过的图片。正常底图/正常样本标记 normal / OK，缺陷样本按各自预期缺陷标签标记 NG。尚未生成的图片不在本次审核范围。`, '整批审核通过', { confirmButtonText: `确认通过 ${ids.length} 张`, cancelButtonText: '返回检查', type: 'warning' })
    } else {
      const answer = await ElMessageBox.prompt(`将选中的 ${ids.length} 张图片标记为不通过，其他图片保持原状态。`, '选中图片审核不通过', { inputType: 'textarea', inputPlaceholder: '填写不通过原因', inputValidator: value => !!value?.trim() && value.length <= 1000 || '请填写1至1000字的不通过原因', confirmButtonText: '确认不通过', cancelButtonText: '取消' })
      reason = answer.value.trim()
    }
  } catch { return }
  busy.value = true
  try { await api(`/batches/${id}/review`, 'PUT', { ids, status, reason }); selected.value = []; emit('refresh'); ElMessage.success(`已审核 ${ids.length} 张图片`) }
  finally { busy.value = false }
}
async function download() {
  if (!batchId.value) return
  exporting.value = true
  try {
    const params = new URLSearchParams({ review: 'APPROVED', batch: batchId.value, defect: defect.value })
    const response = await fetch(`/api/export?${params}`)
    if (!response.ok) { const error = await response.json(); throw new Error(error.message) }
    const url = URL.createObjectURL(await response.blob()), link = document.createElement('a'); link.href = url; link.download = `hamlab-${shortId(batchId.value)}.zip`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '导出失败') } finally { exporting.value = false }
}
</script>
<template>
  <section class="page-heading"><div><h1>批次审核与导出</h1><p>选择生成批次，可整批通过，也可勾选图片标记不通过。姿势底图与缺陷结果均在这里审核。</p></div><el-button type="primary" :disabled="!currentBatch || currentBatch.stage === 'POSE'" :loading="exporting" @click="download">导出本批次已通过样本</el-button></section>
  <div class="panel batch-picker"><label for="review-batch">生成批次</label><el-select id="review-batch" v-model="batchId" filterable aria-label="选择审核批次" placeholder="选择需要审核的批次"><el-option v-for="b in reviewBatches" :key="b.id" :value="b.id" :label="`${shortId(b.id)} · ${b.stage === 'POSE' ? '姿势底图' : '日期缺陷'} · ${new Date(b.created_at).toLocaleString()}`" /></el-select><span class="muted">共 {{ reviewBatches.length }} 个有结果的批次</span></div>
  <template v-if="currentBatch">
    <div class="panel review-batch-summary"><div><b>批次 {{ shortId(batchId) }}</b><span class="muted">已生成 {{ counts.all }} 张 · 待审核 {{ counts.pending }} · 已通过 {{ counts.approved }} · 不通过 {{ counts.rejected }}</span></div><el-button type="success" :loading="busy" :disabled="!batchAssets.length" @click="batchReview('APPROVED')">整批审核通过（{{ counts.all }} 张）</el-button></div>
    <div class="panel filter-bar"><el-select v-model="review" aria-label="审核状态"><el-option label="全部状态" value="ALL" /><el-option label="待审核" value="PENDING" /><el-option label="审核通过" value="APPROVED" /><el-option label="不通过" value="REJECTED" /></el-select><el-select v-if="currentBatch.stage === 'DEFECT'" v-model="defect" clearable placeholder="全部预期缺陷"><el-option v-for="(name,key) in defectNames" :key="key" :label="name" :value="key" /></el-select><el-button :disabled="!results.length" @click="selected = results.map(a => a.id)">全选当前筛选</el-button><el-button :disabled="!selected.length" @click="selected = []">清空选择</el-button><el-button type="danger" plain :disabled="!selected.length" :loading="busy" @click="batchReview('REJECTED')">选中图片不通过（{{ selected.length }}）</el-button></div>
    <p class="export-note">{{ currentBatch.stage === 'POSE' ? '正常底图审核通过后，还需在底图库框选日期区域，才能用于缺陷生成。' : '导出仅包含本批次审核通过的缺陷结果，测试图始终排除。' }}</p>
    <div v-if="!results.length" class="empty-state"><h2>当前筛选下没有图片</h2><p>可切换审核状态查看本批次其他结果。</p></div>
    <el-checkbox-group v-model="selected" class="image-grid review-image-grid"><article v-for="a in results" :key="a.id" class="image-card" :class="{ 'review-selected': selected.includes(a.id) }"><div class="review-image-select"><el-checkbox :value="a.id" :aria-label="`选择图片 ${shortId(a.id)}`">选择图片</el-checkbox></div><div class="image-preview"><el-image :src="imageUrl(a.id,true)" :preview-src-list="results.map(a => imageUrl(a.id))" :initial-index="results.findIndex(item => item.id === a.id)" fit="contain" preview-teleported /><span class="image-source" :class="{test:a.sourceType === 'TEST'}">{{ a.sourceType === 'TEST' ? '测试 / 不导出' : a.role === 'POSE' ? '生成底图' : '生成结果' }}</span></div><div class="image-info"><div class="card-title"><b>{{ shortId(a.id) }}</b><el-tag :type="a.review === 'APPROVED' ? 'success' : a.review === 'REJECTED' ? 'danger' : 'info'" size="small">{{ a.review === 'PENDING' ? '待审核' : statusText[a.review] }}</el-tag></div><p>预期：{{ taskMap.get(a.taskId!)?.params.defect ? defectNames[taskMap.get(a.taskId!)!.params.defect!.type] : '正常底图' }}</p><p>人工标签 {{ a.label || '尚未确认' }} · {{ a.quality || '—' }}</p><p v-if="a.rejectionReason" class="error-text">{{ a.rejectionReason }}</p><div class="card-actions"><el-button size="small" @click="reviewing = a">对照审核</el-button><el-button size="small" @click="regenerate(a)">从同一底图再生成</el-button></div></div></article></el-checkbox-group>
  </template>
  <div v-else class="empty-state"><h2>暂无已生成的批次</h2><p>任务生成并保存图片后，会出现在这里。</p></div>
  <ReviewDialog v-if="reviewing" :asset="reviewing" :assets="assets" @close="reviewing = undefined" @saved="reviewing = undefined; emit('refresh')" />
</template>
