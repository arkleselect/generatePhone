<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, shortId } from '../api'
import type { Task } from '../types'
import ImageDropzone from './ImageDropzone.vue'
const props = defineProps<{ task: Task }>(), emit = defineEmits<{ completed: [] }>()
const result = ref<File[]>([]), actualModel = ref(''), busy = ref(false), reason = ref('')
// Copy only the immutable task prompt; each transfer uses the original fixed input image.
async function copy(text: string) { try { await navigator.clipboard.writeText(text); ElMessage.success('已复制') } catch { ElMessage.warning('剪贴板不可用，请在任务参数中手动复制') } }
async function upload() {
  if (!result.value[0]) return
  busy.value = true
  try { const form = new FormData(); form.append('file', result.value[0]); form.append('actualModel', actualModel.value); form.append('channel','MANUAL_CHATGPT'); await api(`/tasks/${props.task.id}/result`, 'POST', form); emit('completed'); ElMessage.success('原始结果已保存，下一步请人工审核') }
  finally { busy.value = false }
}
async function fail() {
  try { await ElMessageBox.confirm('确认该次生图失败且没有可回填结果后，才标记失败。若已生成，请直接导入图片，避免重复生成。', '记录生成失败') } catch { return }
  await api(`/tasks/${props.task.id}/failure`, 'POST', { reason: reason.value, uncertain: false }); emit('completed')
}
</script>
<template>
  <section class="account-workspace">
    <div class="panel-heading"><div><h3>{{ task.status === 'UNKNOWN' ? '核实已有结果' : '当前等待账号生图' }} · {{ shortId(task.id) }}</h3></div><el-tag type="warning">{{ task.status === 'UNKNOWN' ? '结果待核实' : '等待真实结果' }}</el-tag></div>
    <p class="muted">在「账号设置」登录并开启浏览器执行器后，本任务会自动生成并保存。遇到异常时，可展开下方工具回填已生成的原图。</p>
    <el-collapse><el-collapse-item title="异常恢复 / 手动导入已有结果">
    <div class="queue-actions"><el-button @click="copy(task.prompt)">复制提示词</el-button><a :href="`/api/tasks/${task.id}/bundle`" class="el-button" download>下载任务包</a></div>
    <div class="account-import"><b>回填账号生成的原图</b><div class="form-row"><ImageDropzone v-model="result" :multiple="false" :disabled="busy" compact /><el-input v-model="actualModel" placeholder="实际模型（若可确认；未知请留空）" maxlength="150" /><el-button type="primary" :disabled="!result.length" :loading="busy" @click="upload">保存结果</el-button></div><p class="muted">这里仅导入真实生成结果。导入不会自动审核通过；实际尺寸以图片文件为准。</p></div>
    </el-collapse-item></el-collapse>
    <el-collapse><el-collapse-item title="本次生成失败？记录原因并释放队列"><el-input v-model="reason" maxlength="1000" placeholder="填写失败原因，例如账号额度暂时用尽" /><el-button class="failure-button" type="danger" plain :disabled="!reason.trim()" @click="fail">记录失败</el-button></el-collapse-item></el-collapse>
  </section>
</template>
