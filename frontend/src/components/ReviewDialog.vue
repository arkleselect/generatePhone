<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { api, defectNames, imageUrl, shortId } from '../api'
import type { Asset, Task } from '../types'

const props = defineProps<{ asset: Asset; assets: Asset[]; deep?: boolean; deletable?: boolean; position?: number; total?: number; selected?: boolean }>()
const emit = defineEmits<{ close: []; saved: []; navigate: [step: number]; 'toggle-select': []; delete: [] }>()
const label = ref(props.asset.label || ''), quality = ref(props.asset.quality || (props.asset.role === 'DEFECT_REF' ? 'NG' : '')), reason = ref(props.asset.rejectionReason || '')
const busy = ref(false), zoom = ref(1), zoomBox = ref<HTMLElement>(), task = ref<Task>()
const reviewLabels = computed(() => props.asset.role === 'POSE' ? { normal: '正常底图' } : props.asset.role === 'DEFECT_REF' ? Object.fromEntries(Object.entries(defectNames).filter(([key]) => key !== 'normal')) : defectNames)
const comparisons = computed(() => props.asset.role === 'DEFECT_REF' ? [{ title: '缺陷参考图', id: props.asset.id }] : [{ title: '原始参考图', id: props.asset.rootSourceId }, ...(props.asset.parentPoseId ? [{ title: '当前姿势底图', id: props.asset.parentPoseId }] : []), { title: props.asset.role === 'POSE' ? '待审核底图' : '生成结果', id: props.asset.id }])
// Intended defect is shown as context only; reviewer must explicitly choose the verified label.
onMounted(async () => { if (!props.deep && props.asset.taskId) task.value = await api<Task>(`/tasks/${props.asset.taskId}`) })
async function zoomTo(level: number) {
  zoom.value = level
  await nextTick()
  if (zoomBox.value) {
    zoomBox.value.scrollLeft = (zoomBox.value.scrollWidth - zoomBox.value.clientWidth) / 2
    zoomBox.value.scrollTop = (zoomBox.value.scrollHeight - zoomBox.value.clientHeight) / 2
  }
}
async function review(status: string) {
  if (props.asset.review !== 'PENDING') return
  busy.value = true
  try { await api(`/assets/${props.asset.id}/review`, 'PUT', { status, label: label.value, quality: quality.value, reason: reason.value }); emit('saved') }
  finally { busy.value = false }
}
</script>

<template>
  <el-dialog :model-value="true" :title="`人工审核 · ${shortId(asset.id)}`" :class="{ 'deep-review-dialog': deep }" :width="deep ? 'min(1500px, 98vw)' : 'min(1280px, 96vw)'" @close="emit('close')">
    <el-alert v-if="asset.sourceType === 'TEST'" title="测试图片：仅验证工作流，不代表 AI 生成结果，不能导出为训练样本。" type="warning" :closable="false" />
    <div v-if="deep" ref="zoomBox" class="deep-image-scroll">
      <img :src="imageUrl(asset.id)" :alt="`审核图片 ${shortId(asset.id)}`" :style="{ width: zoom === 1 ? 'auto' : `${zoom * 100}%`, maxWidth: zoom === 1 ? '100%' : 'none', maxHeight: zoom === 1 ? '100%' : 'none' }" @dblclick="zoomTo(zoom === 1 ? 3 : 1)" />
    </div>
    <div v-else class="compare-grid">
      <figure v-for="(item,index) in comparisons" :key="index">
        <figcaption>{{ item.title }} <code>{{ shortId(item.id) }}</code></figcaption>
        <el-image :src="imageUrl(item.id)" :preview-src-list="comparisons.map(c => imageUrl(c.id))" :initial-index="index" fit="contain" preview-teleported />
      </figure>
    </div>
    <div v-if="!deep && asset.role !== 'DEFECT_REF'" class="review-note"><b>检查清单</b><span>指定字符是否正确 · 其他字符是否移位或乱码 · 喷码是否过黑过粗 · 是否继承旧缺陷 · 是否混入额外缺陷 · 产品比例和姿势是否正确</span></div>
    <p v-if="task && !deep" class="muted">生成日期：{{ task.params.baseDate }}；预期效果：{{ task.params.defect ? defectNames[task.params.defect.type] : '正常日期底图' }}；预期字符位置：{{ task.params.defect?.positions.join('、') || '无' }}。下方为独立人工确认标签。</p>
    <el-form label-position="top">
      <div class="form-row">
        <el-form-item label="人工确认缺陷标签（通过时必填）">
          <el-select v-model="label" :disabled="asset.review !== 'PENDING'" filterable :allow-create="asset.role !== 'DEFECT_REF'" default-first-option :placeholder="asset.role === 'DEFECT_REF' ? '选择参考图中的缺陷类别' : '人工确认，支持自定义标签'">
            <el-option v-for="(name,key) in reviewLabels" :key="key" :value="key" :label="name" />
          </el-select>
        </el-form-item>
        <el-form-item label="产品质量判定（与审核状态独立）">
          <el-radio-group v-model="quality" :disabled="asset.review !== 'PENDING'"><el-radio value="OK" :disabled="asset.role === 'DEFECT_REF'">OK · 正常产品</el-radio><el-radio value="NG" :disabled="asset.role === 'POSE'">NG · 缺陷产品</el-radio></el-radio-group>
        </el-form-item>
        <div v-if="deep" class="deep-review-nav">
          <el-button :disabled="position === 1 || busy" @click="emit('navigate', -1)">上一张</el-button>
          <span>{{ position }} / {{ total }}</span>
          <el-button :disabled="position === total || busy" @click="emit('navigate', 1)">下一张</el-button>
        </div>
      </div>
      <div v-if="deep" class="deep-action-row">
        <el-form-item label="不通过原因 / 审核备注"><el-input v-model="reason" :disabled="asset.review !== 'PENDING'" type="textarea" :rows="2" maxlength="1000" /></el-form-item>
        <el-button :type="selected ? 'danger' : 'default'" :disabled="busy" @click="emit('toggle-select')">{{ selected ? '已选待删除 · 取消选择' : '选中待删除' }}</el-button>
        <el-button :disabled="asset.review !== 'PENDING'" :loading="busy" @click="review('PENDING')">暂存待审核</el-button>
        <el-button v-if="deletable" type="danger" plain :loading="busy" @click="emit('delete')">删除不合格图片</el-button>
        <el-button v-else type="danger" plain :disabled="asset.review !== 'PENDING'" :loading="busy" @click="review('REJECTED')">不通过</el-button>
        <el-button type="primary" :disabled="asset.review !== 'PENDING'" :loading="busy" @click="review('APPROVED')">通过审核</el-button>
      </div>
      <el-form-item v-else label="不通过原因 / 审核备注"><el-input v-model="reason" :disabled="asset.review !== 'PENDING'" type="textarea" :rows="2" maxlength="1000" /></el-form-item>
    </el-form>
    <template #footer>
      <template v-if="!deep">
        <span v-if="asset.review !== 'PENDING'" class="muted footer-note">此图片已审核，不能重复审核。</span>
        <el-button :disabled="asset.review !== 'PENDING'" :loading="busy" @click="review('PENDING')">暂存待审核</el-button>
        <el-button v-if="deletable" type="danger" plain :loading="busy" @click="emit('delete')">删除不合格图片</el-button>
        <el-button v-else type="danger" plain :disabled="asset.review !== 'PENDING'" :loading="busy" @click="review('REJECTED')">不通过</el-button>
        <el-button type="primary" :disabled="asset.review !== 'PENDING'" :loading="busy" @click="review('APPROVED')">通过审核</el-button>
      </template>
    </template>
  </el-dialog>
</template>
