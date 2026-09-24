<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, shortId } from '../api'
import type { Task } from '../types'
import ImageDropzone from './ImageDropzone.vue'
const props = defineProps<{ task: Task }>(), emit = defineEmits<{ completed: [] }>()
const result = ref<File[]>([]), actualModel = ref(''), busy = ref(false)
// Copy only the immutable task prompt; each transfer uses the original fixed input image.
async function copy(text: string) { try { await navigator.clipboard.writeText(text); ElMessage.success('已复制') } catch { ElMessage.warning('剪贴板不可用，请在任务参数中手动复制') } }
async function upload() {
  if (!result.value[0]) return
  busy.value = true
  try { const form = new FormData(); form.append('file', result.value[0]); form.append('actualModel', actualModel.value); form.append('channel','MANUAL_CHATGPT'); await api(`/tasks/${props.task.id}/result`, 'POST', form); emit('completed'); ElMessage.success('原始结果已保存，下一步请人工审核') }
  finally { busy.value = false }
}
async function fail() {
  try { await ElMessageBox.confirm('请先核实该任务没有生成图片，也没有仍在进行的生成请求。确认后将任务标记为失败并释放队列，不会重新生图。随后可删除无生成图片的暂停批次。已有结果请使用下方导入入口。', '确认无结果并结束任务', { confirmButtonText: '已核实，结束任务', cancelButtonText: '返回检查', type: 'warning' }) } catch { return }
  busy.value = true
  try {
    const worker = await api<{ enabled: boolean; phase: string }>('/browser/status')
    if (worker.enabled || worker.phase === 'RUNNING') { ElMessage.warning('请先在账号设置暂停执行器，并等待当前生成结束后处理'); return }
    if (props.task.status === 'UNKNOWN') await api(`/tasks/${props.task.id}/resolve`, 'POST', { verifiedNotAccepted: true })
    else await api(`/tasks/${props.task.id}/failure`, 'POST', { reason: '人工已核实无生成结果，结束等待并释放队列', uncertain: false })
    emit('completed'); ElMessage.success('任务已结束，可删除无生成图片的暂停批次')
  } finally { busy.value = false }
}
</script>
<template>
  <section class="account-workspace">
    <div class="panel-heading"><div><h3>{{ task.status === 'UNKNOWN' ? '核实已有结果' : '当前等待账号生图' }} · {{ shortId(task.id) }}</h3></div><el-tag type="warning">{{ task.status === 'UNKNOWN' ? '结果待核实' : '等待真实结果' }}</el-tag></div>
    <p class="muted">在「账号设置」登录并开启账号执行器后，本任务会自动生成并保存。遇到异常时，可展开下方工具回填已生成的原图。</p>
    <div class="queue-actions"><el-button type="danger" plain :loading="busy" @click="fail">确认无结果，结束任务</el-button><span class="muted">不再执行此任务时，先核实并结束任务，再删除批次。</span></div>
    <el-collapse><el-collapse-item title="异常恢复 / 手动导入已有结果">
    <div class="queue-actions"><el-button @click="copy(task.prompt)">复制提示词</el-button><a :href="`/api/tasks/${task.id}/bundle`" class="el-button" download>下载任务包</a></div>
    <div class="account-import"><b>回填账号生成的原图</b><div class="form-row"><ImageDropzone v-model="result" :multiple="false" :disabled="busy" compact /><el-input v-model="actualModel" placeholder="实际模型（若可确认；未知请留空）" maxlength="150" /><el-button type="primary" :disabled="!result.length" :loading="busy" @click="upload">保存结果</el-button></div><p class="muted">这里仅导入真实生成结果。导入不会自动审核通过；实际尺寸以图片文件为准。</p></div>
    </el-collapse-item></el-collapse>
  </section>
</template>
