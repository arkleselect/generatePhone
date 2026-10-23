<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api, defectNames, imageUrl } from '../api'
import type { Annotation, Asset, Roi } from '../types'

const props = defineProps<{ asset: Asset }>(), emit = defineEmits<{ saved: [] }>()
const boxes = ref<Annotation[]>(props.asset.annotations.map(a => ({ classId: a.classId, box: { ...a.box } })))
const classId = ref(props.asset.label && props.asset.label !== 'normal' && defectNames[props.asset.label] ? props.asset.label : '')
const draft = ref<Roi>(), start = ref<{ x: number; y: number }>(), surface = ref<HTMLElement>(), viewport = ref<HTMLElement>(), busy = ref(false), scale = ref(1)
let fitWidth = 0
let zoomSequence = 0
const classes = computed(() => Object.entries(defectNames).filter(([id]) => id !== 'normal'))
async function setZoomAt(x: number, y: number, next: number) {
  const image = surface.value?.querySelector('img'), view = viewport.value, element = surface.value
  if (!image?.clientWidth || !view || !element) return
  if (!fitWidth) fitWidth = image.clientWidth
  const before = element.getBoundingClientRect()
  const relativeX = Math.max(0, Math.min(1, (x-before.left)/before.width))
  const relativeY = Math.max(0, Math.min(1, (y-before.top)/before.height))
  const bounded = Math.max(1, Math.min(6, next))
  if (Math.abs(bounded-scale.value) < 0.00001) return
  const sequence = ++zoomSequence
  scale.value = bounded
  await nextTick()
  if (sequence !== zoomSequence) return
  const after = element.getBoundingClientRect()
  view.scrollLeft += after.left + relativeX*after.width - x
  view.scrollTop += after.top + relativeY*after.height - y
}
function wheel(e: WheelEvent) {
  if (!e.metaKey) return
  e.preventDefault()
  const delta = e.deltaY * (e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? viewport.value!.clientHeight : 1)
  void setZoomAt(e.clientX, e.clientY, scale.value * Math.exp(-delta * 0.0015))
}
function doubleClick(e: MouseEvent) {
  const width = fitWidth || surface.value?.querySelector('img')?.clientWidth || props.asset.width
  void setZoomAt(e.clientX, e.clientY, scale.value > 1 ? 1 : props.asset.width / width)
}
function point(e: PointerEvent) {
  const r = surface.value!.getBoundingClientRect()
  return { x: Math.max(0, Math.min(1, (e.clientX-r.left)/r.width)), y: Math.max(0, Math.min(1, (e.clientY-r.top)/r.height)) }
}
function down(e: PointerEvent) {
  if (!classId.value) { ElMessage.warning('请先选择缺陷类别'); return }
  start.value = point(e); surface.value?.setPointerCapture(e.pointerId)
}
function move(e: PointerEvent) {
  if (!start.value) return
  const p = point(e)
  draft.value = { x: Math.min(p.x,start.value.x), y: Math.min(p.y,start.value.y), width: Math.abs(p.x-start.value.x), height: Math.abs(p.y-start.value.y) }
}
function up(e: PointerEvent) {
  if (!start.value) return
  move(e); start.value = undefined
  if (draft.value && draft.value.width*props.asset.width >= 2 && draft.value.height*props.asset.height >= 2) {
    if (boxes.value.length >= 20) ElMessage.warning('每张图片最多20个框')
    else boxes.value.push({ classId: classId.value, box: draft.value })
  }
  draft.value = undefined
}
function style(box: Roi) { return { left: `${box.x*100}%`, top: `${box.y*100}%`, width: `${box.width*100}%`, height: `${box.height*100}%` } }
async function save() {
  busy.value = true
  try { await api(`/assets/${props.asset.id}/annotations`, 'PUT', boxes.value); ElMessage.success('缺陷框已保存'); emit('saved') }
  finally { busy.value = false }
}
</script>
<template>
  <p class="muted">先选类别，再在原图上拖拽矩形；按住 ⌘ 滚动鼠标滚轮可缩放，双击图片可切换原始尺寸。缺码框住应有字符的位置及邻近字符。</p>
  <div class="annotation-toolbar"><el-select v-model="classId" placeholder="选择缺陷类别" filterable><el-option v-for="[id,name] in classes" :key="id" :value="id" :label="name" /></el-select><span>已画 {{ boxes.length }} 个框</span></div>
  <div ref="viewport" class="annotation-viewport" @wheel="wheel">
    <div ref="surface" class="roi-surface annotation-surface" :style="scale > 1 ? { maxWidth: 'none', margin: '0' } : {}" @dblclick="doubleClick" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="start = undefined; draft = undefined">
      <img :src="imageUrl(asset.id)" :alt="`标注图片 ${asset.id}`" :style="scale > 1 ? { width: `${fitWidth*scale}px`, maxWidth: 'none', maxHeight: 'none' } : {}" draggable="false">
      <div v-for="(a,i) in boxes" :key="i" class="roi-box" :style="style(a.box)"><span>{{ defectNames[a.classId] || a.classId }}</span></div>
      <div v-if="draft" class="roi-box" :style="style(draft)"><span>{{ defectNames[classId] }}</span></div>
    </div>
  </div>
  <div class="annotation-list"><div v-for="(a,i) in boxes" :key="i"><span>{{ i+1 }}. {{ defectNames[a.classId] || a.classId }}</span><el-button size="small" type="danger" text @click="boxes.splice(i,1)">删除此框</el-button></div></div>
  <div class="dialog-actions"><span class="muted">{{ asset.width }} × {{ asset.height }} · 图片 {{ asset.id.slice(0,8).toUpperCase() }}</span><el-button type="primary" :loading="busy" @click="save">保存标注</el-button></div>
</template>
