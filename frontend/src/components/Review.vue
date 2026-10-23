<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, defectNames, imageUrl, shortId, statusText } from '../api'
import type { Asset, Batch, Detail, Task } from '../types'
import ReviewDialog from './ReviewDialog.vue'
import AnnotationEditor from './AnnotationEditor.vue'
const props = defineProps<{ assets: Asset[] }>(), emit = defineEmits<{ refresh: []; draft: [Detail] }>()
const review = ref('ALL'), defect = ref(''), reviewing = ref<Asset>(), exporting = ref(false), busy = ref(false)
const deepReview = ref(false)
const annotating = ref<Asset>(), exportingDetection = ref(false)
const batches = ref<Batch[]>([]), tasks = ref<Task[]>([]), batchId = ref(''), selected = ref<string[]>([])
const taskMap = computed(() => new Map(tasks.value.map(t => [t.id, t])))
const generated = computed(() => props.assets.filter(a => a.taskId && taskMap.value.has(a.taskId)))
const reviewBatches = computed(() => batches.value.filter(b => generated.value.some(a => taskMap.value.get(a.taskId!)?.batchId === b.id)))
function batchLabel(batch: Batch) {
  if (batch.stage === 'POSE') return '阶段 A · 正常姿势'
  const types = [...new Set(tasks.value.filter(t => t.batchId === batch.id).map(t => t.params.defect?.type).filter((type): type is string => !!type))]
  return `阶段 B · ${types.length ? types.map(type => defectNames[type] || type).join('、') : '日期缺陷'}`
}
const currentBatch = computed(() => reviewBatches.value.find(b => b.id === batchId.value))
const batchAssets = computed(() => generated.value.filter(a => taskMap.value.get(a.taskId!)?.batchId === batchId.value))
const results = computed(() => batchAssets.value.filter(a => review.value === 'ALL' || a.review === review.value).filter(a => !defect.value || taskMap.value.get(a.taskId!)?.params.defect?.type === defect.value))
const counts = computed(() => ({ total: tasks.value.filter(t => t.batchId === batchId.value).length, all: batchAssets.value.length, annotated: batchAssets.value.filter(a => a.annotations.length > 0).length, pending: batchAssets.value.filter(a => a.review === 'PENDING').length, approved: batchAssets.value.filter(a => a.review === 'APPROVED').length, rejected: batchAssets.value.filter(a => a.review === 'REJECTED').length }))
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
function moveReview(step: number) {
  const index = results.value.findIndex(a => a.id === reviewing.value?.id)
  reviewing.value = results.value[index + step] || reviewing.value
}
function toggleReviewSelection() {
  const id = reviewing.value?.id
  if (!id) return
  selected.value = selected.value.includes(id) ? selected.value.filter(item => item !== id) : [...selected.value, id]
}
function reviewed() {
  const index = results.value.findIndex(a => a.id === reviewing.value?.id)
  reviewing.value = deepReview.value ? results.value[index + 1] : undefined
  if (!reviewing.value) deepReview.value = false
  emit('refresh')
}
async function batchReview() {
  const id = batchId.value
  const ids = batchAssets.value.filter(a => a.review === 'PENDING').map(a => a.id)
  if (!id || !ids.length) return
  try {
    await ElMessageBox.confirm(`确认本批次当前待审核的 ${ids.length} 张图片均符合各自任务要求？正常底图/正常样本标记 normal / OK，缺陷样本按各自预期缺陷标签标记 NG。已审核及尚未生成的图片不在本次范围。`, '整批审核通过', { confirmButtonText: `确认通过 ${ids.length} 张`, cancelButtonText: '返回检查', type: 'warning' })
  } catch { return }
  busy.value = true
  try { await api(`/batches/${id}/review`, 'PUT', { ids, status: 'APPROVED', reason: '' }); selected.value = []; emit('refresh'); ElMessage.success(`已审核 ${ids.length} 张图片`) }
  finally { busy.value = false }
}
async function deleteOutputs(ids = [...selected.value]) {
  if (!batchId.value || !ids.length) return
  try { await ElMessageBox.confirm(`永久删除选中的 ${ids.length} 张不合格图片？任务记录会保留，此操作无法撤销。`, '删除不合格图片', { type: 'warning', confirmButtonText: `删除 ${ids.length} 张`, cancelButtonText: '保留图片' }) } catch { return }
  busy.value = true
  try {
    await api(`/batches/${batchId.value}/outputs/delete`, 'POST', ids)
    selected.value = selected.value.filter(id => !ids.includes(id))
    if (reviewing.value && ids.includes(reviewing.value.id)) {
      const next = results.value.find(a => !ids.includes(a.id))
      reviewing.value = deepReview.value ? next : undefined
      if (!next) deepReview.value = false
    }
    emit('refresh'); ElMessage.success(`已删除 ${ids.length} 张图片`)
  } finally { busy.value = false }
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
async function downloadDetection() {
  if (!batchId.value) return
  exportingDetection.value = true
  try {
    const response = await fetch(`/api/export/detection?batch=${encodeURIComponent(batchId.value)}`)
    if (!response.ok) { const error = await response.json(); throw new Error(error.message) }
    const url = URL.createObjectURL(await response.blob()), link = document.createElement('a')
    link.href = url; link.download = `hamlab-detection-${shortId(batchId.value)}.zip`; link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '检测标注导出失败') }
  finally { exportingDetection.value = false }
}
</script>
<template>
  <section class="page-heading"><div><h1>批次审核与导出</h1><p>选择生成批次，可整批通过，也可在深度审核中挑出不合格图片并删除。姿势底图与缺陷结果均在这里审核。</p></div><div class="queue-actions"><el-button :disabled="!currentBatch || currentBatch.stage === 'POSE' || !batchAssets.some(a => a.annotations.length)" :loading="exportingDetection" @click="downloadDetection">导出检测标注</el-button><el-button type="primary" :disabled="!currentBatch || currentBatch.stage === 'POSE'" :loading="exporting" @click="download">导出本批次已通过样本</el-button></div></section>
  <div class="panel batch-picker"><label for="review-batch">生成批次</label><el-select id="review-batch" v-model="batchId" filterable aria-label="选择审核批次" placeholder="选择需要审核的批次"><el-option v-for="b in reviewBatches" :key="b.id" :value="b.id" :label="`${shortId(b.id)} · ${batchLabel(b)} · ${new Date(b.created_at).toLocaleString()}`" /></el-select><span class="muted">共 {{ reviewBatches.length }} 个有结果的批次</span></div>
  <template v-if="currentBatch">
    <div class="panel review-batch-summary"><div><b>批次 {{ shortId(batchId) }}</b><span class="muted">计划共 {{ counts.total }} 张 · 已生成 {{ counts.all }} 张 · 已标注 {{ counts.annotated }} 张 · 待审核 {{ counts.pending }} · 已通过 {{ counts.approved }} · 不通过 {{ counts.rejected }}</span></div><el-button type="success" :loading="busy" :disabled="!counts.pending" @click="batchReview">整批审核通过（{{ counts.pending }} 张待审核）</el-button></div>
    <div class="panel filter-bar"><el-select v-model="review" aria-label="审核状态"><el-option label="全部状态" value="ALL" /><el-option label="待审核" value="PENDING" /><el-option label="审核通过" value="APPROVED" /><el-option label="不通过" value="REJECTED" /></el-select><el-select v-if="currentBatch.stage === 'DEFECT'" v-model="defect" clearable placeholder="全部预期缺陷"><el-option v-for="(name,key) in defectNames" :key="key" :label="name" :value="key" /></el-select><el-button :disabled="!results.length" @click="deepReview = true; reviewing = results.find(a => a.review === 'PENDING') || results[0]">深度审核</el-button><el-button :disabled="!results.length" @click="selected = results.map(a => a.id)">全选当前筛选</el-button><el-button :disabled="!selected.length" @click="selected = []">清空选择</el-button><el-button type="danger" plain :disabled="!selected.length || selected.length > 200" :loading="busy" @click="deleteOutputs()">删除选中的不合格图片（{{ selected.length }}）</el-button></div>
    <p class="export-note">{{ currentBatch.stage === 'POSE' ? '正常底图审核通过后，还需在底图库框选日期区域，才能用于缺陷生成。' : '导出仅包含本批次审核通过的缺陷结果，测试图始终排除。' }}</p>
    <div v-if="!results.length" class="empty-state"><h2>当前筛选下没有图片</h2><p>可切换审核状态查看本批次其他结果。</p></div>
    <el-checkbox-group v-model="selected" class="image-grid review-image-grid"><article v-for="a in results" :key="a.id" class="image-card" :class="{ 'review-selected': selected.includes(a.id) }"><div class="review-image-select"><el-checkbox :value="a.id" :aria-label="`选择图片 ${shortId(a.id)}`">选择图片</el-checkbox></div><div class="image-preview"><el-image :src="imageUrl(a.id,true)" :preview-src-list="results.map(a => imageUrl(a.id))" :initial-index="results.findIndex(item => item.id === a.id)" fit="contain" preview-teleported /><span class="image-source" :class="{test:a.sourceType === 'TEST'}">{{ a.sourceType === 'TEST' ? '测试 / 不导出' : a.role === 'POSE' ? '生成底图' : '生成结果' }}</span><span v-if="a.annotations.length" class="annotation-badge">已标注 {{ a.annotations.length }} 框</span></div><div class="image-info"><div class="card-title"><b>{{ shortId(a.id) }}</b><el-tag :type="a.review === 'APPROVED' ? 'success' : a.review === 'REJECTED' ? 'danger' : 'info'" size="small">{{ a.review === 'PENDING' ? '待审核' : statusText[a.review] }}</el-tag></div><p>预期：{{ taskMap.get(a.taskId!)?.params.defect ? defectNames[taskMap.get(a.taskId!)!.params.defect!.type] : '正常底图' }}</p><p>人工标签 {{ a.label || '尚未确认' }} · {{ a.quality || '—' }}</p><p v-if="a.rejectionReason" class="error-text">{{ a.rejectionReason }}</p><div class="card-actions"><el-button size="small" :disabled="a.review !== 'PENDING'" @click="deepReview = false; reviewing = a">{{ a.review === 'PENDING' ? '对照审核' : '已审核' }}</el-button><el-button v-if="a.role === 'RESULT' && a.review === 'APPROVED' && a.quality === 'NG'" size="small" @click="annotating = a">{{ a.annotations.length ? '修改缺陷框' : '标注缺陷框' }}</el-button><el-button size="small" @click="regenerate(a)">从同一底图再生成</el-button></div></div></article></el-checkbox-group>
  </template>
  <div v-else class="empty-state"><h2>暂无已生成的批次</h2><p>任务生成并保存图片后，会出现在这里。</p></div>
  <ReviewDialog v-if="reviewing" :key="reviewing.id" :asset="reviewing" :assets="assets" :deep="deepReview" :deletable="true" :position="results.findIndex(a => a.id === reviewing?.id) + 1" :total="results.length" :selected="selected.includes(reviewing.id)" @navigate="moveReview" @toggle-select="toggleReviewSelection" @delete="deleteOutputs([reviewing!.id])" @close="reviewing = undefined; deepReview = false" @saved="reviewed" />
  <el-dialog :model-value="!!annotating" title="缺陷矩形框标注" width="min(1200px, 96vw)" top="2vh" @close="annotating = undefined"><AnnotationEditor v-if="annotating" :asset="annotating" @saved="annotating = undefined; emit('refresh')" /></el-dialog>
</template>
