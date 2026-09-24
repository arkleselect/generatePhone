<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
// Shared file selection for source photos and account results; upload remains explicitly confirmed.
const model = defineModel<File[]>({ required: true })
const props = withDefaults(defineProps<{ multiple?: boolean; disabled?: boolean; compact?: boolean; showList?: boolean }>(), { multiple: true, disabled: false, compact: false, showList: true })
const emit = defineEmits<{ selected: [] }>()
const picker = ref<HTMLInputElement>(), depth = ref(0), previews = ref<{ file: File; url: string }[]>([])
function release() { previews.value.forEach(item => URL.revokeObjectURL(item.url)) }
watch(model, files => { release(); previews.value = props.showList ? files.map(file => ({ file, url: URL.createObjectURL(file) })) : [] }, { immediate: true })
onUnmounted(release)
// Validate both drag and file-picker input in one place; the backend still validates decoded images.
function select(incoming: File[]) {
  if (props.disabled) return
  const valid: File[] = [], rejected: string[] = []
  for (const file of incoming) {
    const supported = ['image/jpeg', 'image/png'].includes(file.type) || (!file.type && /\.(jpe?g|png)$/i.test(file.name))
    if (!supported || file.size === 0 || file.size > 20 * 1024 * 1024) rejected.push(file.name)
    else valid.push(file)
  }
  if (rejected.length) ElMessage.warning(`${rejected.length} 个文件未加入：仅支持非空 JPG/PNG，每张不超过20MB`)
  if (!valid.length) return
  if (!props.multiple && valid.length > 1) { ElMessage.warning('此处每次只能导入一张结果图'); return }
  const merged = props.multiple ? [...model.value] : []
  for (const file of valid) if (!merged.some(item => item.name === file.name && item.size === file.size && item.lastModified === file.lastModified)) merged.push(file)
  model.value = merged; emit('selected')
}
function open() { if (!props.disabled) picker.value?.click() }
function pick(event: Event) { const input = event.target as HTMLInputElement; select(Array.from(input.files || [])); input.value = '' }
function drop(event: DragEvent) { depth.value = 0; select(Array.from(event.dataTransfer?.files || [])) }
</script>
<template>
  <div class="photo-upload">
    <input ref="picker" type="file" accept="image/jpeg,image/png" :multiple="multiple" :disabled="disabled" class="file-input-hidden" tabindex="-1" @change="pick">
    <div :class="['photo-dropzone', { dragging: depth > 0 && !disabled, compact, disabled }]" role="button" :tabindex="disabled ? -1 : 0" :aria-disabled="disabled" :aria-label="multiple ? '拖拽照片到这里，或点击选择图片' : '拖拽生成结果到这里，或点击选择图片'" @click="open" @keydown.enter.prevent="open" @keydown.space.prevent="open" @dragenter.prevent="depth++" @dragover.prevent @dragleave.prevent="depth = Math.max(0, depth - 1)" @drop.prevent.stop="drop">
      <span class="drop-symbol">＋</span><div><strong>{{ multiple ? '拖拽照片到这里，或点击选择' : '拖拽生成结果到这里，或点击选择' }}</strong><small>JPG / JPEG / PNG · 每张不超过20MB{{ multiple ? ' · 支持多张' : '' }}</small></div>
    </div>
    <div v-if="showList && previews.length" class="upload-files"><div v-for="(item, index) in previews" :key="item.url" class="upload-file"><img :src="item.url" alt="待上传图片预览"><span :title="item.file.name">{{ item.file.name }}<small>{{ (item.file.size / 1024).toFixed(0) }} KB</small></span><el-button text type="danger" :disabled="disabled" :aria-label="`移除 ${item.file.name}`" @click="model = model.filter((_, i) => i !== index)">移除</el-button></div></div>
  </div>
</template>
