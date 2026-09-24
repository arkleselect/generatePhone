<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api, imageUrl } from '../api'
import type { Asset, Roi } from '../types'
const props = defineProps<{ asset: Asset }>(), emit = defineEmits<{ saved: [] }>()
const box = ref<Roi>(), start = ref<{ x: number; y: number }>(), surface = ref<HTMLElement>(), busy = ref(false)
watch(() => props.asset, a => { box.value = a.roi ? { ...a.roi } : undefined }, { immediate: true })
const style = computed(() => box.value ? { left: `${box.value.x*100}%`, top: `${box.value.y*100}%`, width: `${box.value.width*100}%`, height: `${box.value.height*100}%` } : {})
// Pointer positions are normalized to the actual displayed image, so resized previews retain coordinates.
function point(e: PointerEvent) { const r = surface.value!.getBoundingClientRect(); return { x: Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)), y: Math.max(0,Math.min(1,(e.clientY-r.top)/r.height)) } }
function down(e: PointerEvent) { start.value = point(e); surface.value?.setPointerCapture(e.pointerId) }
function move(e: PointerEvent) { if (!start.value) return; const p = point(e); box.value = { x: Math.min(p.x,start.value.x), y: Math.min(p.y,start.value.y), width: Math.abs(p.x-start.value.x), height: Math.abs(p.y-start.value.y) } }
function up(e: PointerEvent) { move(e); start.value = undefined }
async function save() { busy.value = true; try { await api(`/assets/${props.asset.id}/roi`, 'PUT', box.value); emit('saved') } finally { busy.value = false } }
</script>
<template>
  <p class="muted">在图上拖拽框选日期及紧邻区域。每张底图独立确认；框选区域不是精确缺陷标注。</p>
  <div ref="surface" class="roi-surface" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="start = undefined">
    <img :src="imageUrl(asset.id)" alt="框选日期编辑范围" draggable="false"><div v-if="box" class="roi-box" :style="style"><span>日期编辑区域</span></div>
  </div>
  <div class="dialog-actions"><span class="muted">{{ box ? `x ${box.x.toFixed(3)} / y ${box.y.toFixed(3)} / w ${box.width.toFixed(3)} / h ${box.height.toFixed(3)}` : '尚未框选' }}</span><el-button type="primary" :disabled="!box || box.width <= 0 || box.height <= 0" :loading="busy" @click="save">保存日期区域</el-button></div>
</template>
