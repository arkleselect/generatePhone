<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { initialDate, api, imageUrl, shortId, statusText, poseNames } from '../api'
import type { Asset } from '../types'
import RoiEditor from './RoiEditor.vue'
import ImageDropzone from './ImageDropzone.vue'
import ReviewDialog from './ReviewDialog.vue'
const props = defineProps<{ assets: Asset[] }>(), emit = defineEmits<{ refresh: []; create: [] }>()
const tab = ref('SOURCE'), uploadOpen = ref(false), role = ref('SOURCE'), date = ref(initialDate()), files = ref<File[]>([]), busy = ref(false)
const deleting = ref<string>()
const region = ref<Asset>(), reviewing = ref<Asset>()
const compact = ref(false), selected = ref<string[]>([]), page = ref(1), deletingMany = ref(false)
// Keep selection scoped to the active library and remove ids no longer present after refresh.
watch(tab, () => { selected.value = []; page.value = 1 })
watch(() => props.assets, () => { selected.value = selected.value.filter(id => props.assets.some(a => a.id === id)); page.value = Math.min(page.value, Math.max(1, Math.ceil(visible.value.length / 48))) })
const visible = computed(() => props.assets.filter(a => a.role === tab.value))
const approved = computed(() => props.assets.filter(a => a.role === 'POSE' && a.review === 'APPROVED').length)
const pageAssets = computed(() => visible.value.slice((page.value-1)*48,page.value*48))
function selectPage() { selected.value = [...new Set([...selected.value, ...pageAssets.value.map(a => a.id)])] }
// Reuse the backend reference guards; atomic failure keeps the entire selection intact.
async function deleteSelected() {
  try { await ElMessageBox.confirm(`确认删除选中的 ${selected.value.length} 张图片？如有已引用图片，本次全部保留。`, '批量删除', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }) } catch { return }
  deletingMany.value = true
  try { await api('/assets/delete', 'POST', selected.value); selected.value = []; emit('refresh'); ElMessage.success('所选图片已删除') }
  catch { /* Shared API client displays the reason; keep selection for correction. */ }
  finally { deletingMany.value = false }
}
// Upload files separately so one invalid image does not discard other successful uploads.
async function upload() {
  busy.value = true; const failed: File[] = []; let successes = 0
  try {
    for (const file of files.value) {
      const form = new FormData(); form.append('file', file); form.append('role', role.value); form.append('baseDate', date.value)
      try { await api('/assets', 'POST', form); successes++ } catch { failed.push(file) }
    }
    files.value = failed; emit('refresh'); if (successes) ElMessage.success(`已上传 ${successes} 张`)
    if (!failed.length) { uploadOpen.value = false; tab.value = role.value }
  } finally { busy.value = false }
}
// Confirm destructive removal and let the shared client display reference or network errors.
async function deleteSource(asset: Asset) {
  if (deleting.value) return
  deleting.value = asset.id
  try {
    try {
      await ElMessageBox.confirm(`确认删除参考图 ${shortId(asset.id)}？删除后无法恢复。`, '删除参考图', {
        type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
      })
    } catch { return } // Closing the confirmation makes no request.
    try {
      await api(`/assets/${encodeURIComponent(asset.id)}`, 'DELETE')
      emit('refresh'); ElMessage.success('参考图已删除')
    } catch { /* The shared API client already displays the failure reason. */ }
  } finally { deleting.value = undefined }
}
</script>
<template>
  <section class="page-heading"><div><h1>参考图与姿势底图库</h1></div><el-button type="primary" size="large" @click="role = tab; uploadOpen = true">＋ 上传图片</el-button></section>

  <ImageDropzone v-model="files" compact :show-list="false" :disabled="busy" @selected="role = tab; uploadOpen = true" />
  <div class="section-toolbar"><el-radio-group v-model="tab"><el-radio-button value="SOURCE">原始参考图 {{ assets.filter(a => a.role === 'SOURCE').length }}</el-radio-button><el-radio-button value="POSE">姿势底图库 {{ assets.filter(a => a.role === 'POSE').length }}</el-radio-button></el-radio-group><span class="muted">{{ approved }} 张底图已通过审核</span></div>
  <div v-if="!visible.length" class="empty-state"><div class="empty-frame"><span>＋</span></div><h2>{{ tab === 'SOURCE' ? '暂无参考图' : '暂无姿势底图' }}</h2><p>{{ tab === 'SOURCE' ? '支持 JPG / JPEG / PNG，多张上传；原图与缩略图独立保存。' : '可生成新姿势，也可直接上传真实合格照片，减少生图调用。' }}</p><el-button @click="role = tab; uploadOpen = true">上传{{ tab === 'SOURCE' ? '参考图' : '真实底图' }}</el-button></div>
  <div class="section-toolbar"><div class="queue-actions"><el-button :type="compact ? 'primary' : 'default'" @click="compact = !compact">小图模式{{ compact ? ' · 已开启' : '' }}</el-button><el-button @click="selectPage">选择本页</el-button><el-button :disabled="!selected.length" @click="selected = []">清空选择</el-button><el-button type="danger" plain :disabled="!selected.length || selected.length > 200 || !!deleting" :loading="deletingMany" @click="deleteSelected">批量删除 {{ selected.length || '' }}</el-button></div></div>
  <div :class="['image-grid', { 'image-grid-compact': compact }]"><article v-for="asset in pageAssets" :key="asset.id" class="image-card"><div class="image-preview"><el-image :src="imageUrl(asset.id, true)" :preview-src-list="[imageUrl(asset.id)]" fit="contain" preview-teleported /><span class="image-source" :class="{ test: asset.sourceType === 'TEST' }">{{ { REAL: '真实上传', AI: 'AI 合成', TEST: '测试图片' }[asset.sourceType] }}</span></div><div class="image-info"><el-checkbox-group v-model="selected" :disabled="deletingMany"><el-checkbox :value="asset.id">选择</el-checkbox></el-checkbox-group><div class="card-title"><b>{{ shortId(asset.id) }}</b><el-tag v-if="tab === 'POSE'" :type="asset.review === 'APPROVED' ? 'success' : asset.review === 'REJECTED' ? 'danger' : 'info'" size="small">{{ asset.review === 'PENDING' ? '待审核' : statusText[asset.review] }}</el-tag></div><p v-if="!compact">{{ asset.width }} × {{ asset.height }} <span>· {{ (asset.fileSize / 1024).toFixed(0) }} KB</span></p><p v-if="!compact">日期 {{ asset.baseDate }} · {{ poseNames[asset.pose.kind] }}</p><div v-if="tab === 'POSE'" class="card-actions"><el-button size="small" @click="reviewing = asset">审核底图</el-button><el-button size="small" @click="region = asset">{{ asset.roi ? '修改日期区域' : '框选日期区域' }}</el-button></div><div v-else class="card-actions"><el-button size="small" type="danger" plain :loading="deleting === asset.id" :disabled="!!deleting && deleting !== asset.id" @click="deleteSource(asset)">删除参考图</el-button></div></div></article></div>
  <el-pagination v-if="visible.length > 48" v-model:current-page="page" :page-size="48" :total="visible.length" layout="prev, pager, next, total" />
  <el-dialog v-model="uploadOpen" title="上传真实图片" width="min(560px, 94vw)" :close-on-click-modal="!busy" :close-on-press-escape="!busy" :show-close="!busy"><el-form label-position="top" :disabled="busy"><el-form-item label="图片用途"><el-radio-group v-model="role"><el-radio value="SOURCE">原始参考图</el-radio><el-radio value="POSE">真实合格底图</el-radio></el-radio-group></el-form-item><el-form-item label="完整生产日期"><el-input v-model="date" maxlength="32" /></el-form-item><ImageDropzone v-model="files" :disabled="busy" /><p class="muted">{{ files.length }} 张待上传。真实底图上传后仍需人工审核和日期区域确认。</p></el-form><template #footer><el-button type="primary" :loading="busy" :disabled="!files.length" @click="upload">上传 {{ files.length }} 张图片</el-button></template></el-dialog>
  <el-dialog :model-value="!!region" title="确认日期编辑区域" width="min(1000px, 94vw)" @close="region = undefined"><RoiEditor v-if="region" :asset="region" @saved="region = undefined; emit('refresh')" /></el-dialog>
  <ReviewDialog v-if="reviewing" :asset="reviewing" :assets="assets" @close="reviewing = undefined" @saved="reviewing = undefined; emit('refresh')" />
</template>
