<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import AccountTask from './AccountTask.vue'
import { api, imageUrl, defectNames, poseNames, shortId, statusText } from '../api'
import type { Asset, Batch, Detail, Task } from '../types'
const props = defineProps<{ initial?: Detail; assets: Asset[] }>(), emit = defineEmits<{ refresh: []; draft: [Detail] }>()
const list = ref<Batch[]>([]), detail = ref<Detail>(), busy = ref(false), promptTask = ref<Task>(), timer = ref<ReturnType<typeof setTimeout>>()
const filter = ref('ALL'), taskPage = ref(1)
const executor = ref<{ phase: string; enabled: boolean; taskId?: string; message: string }>()
const filtered = computed(() => (detail.value?.tasks || []).filter(t => filter.value === 'ALL' || (filter.value === 'WAITING' ? ['DRAFT','PENDING'].includes(t.status) : filter.value === 'CURRENT' ? ['RUNNING','AWAITING_IMAGE'].includes(t.status) : filter.value === 'FAILED' ? ['FAILED','UNKNOWN'].includes(t.status) : t.status === filter.value)))
const pageTasks = computed(() => filtered.value.slice((taskPage.value-1)*30,taskPage.value*30))
const current = computed(() => detail.value?.tasks.find(t => ['RUNNING','AWAITING_IMAGE'].includes(t.status)))
watch([filter, () => detail.value?.batch.id], () => { taskPage.value = 1 })
let stopped = false
const stats = computed(() => { const tasks = detail.value?.tasks || []; return [{ name: '总数', count: tasks.length }, ...['PENDING','AWAITING_IMAGE','SUCCEEDED','FAILED','UNKNOWN'].map(s => ({ name: statusText[s], count: tasks.filter(t => t.status === s).length })), { name: '待审核', count: tasks.filter(t => props.assets.some(a => a.id === t.outputId && a.review === 'PENDING')).length }] })
const progress = computed(() => { const tasks = detail.value?.tasks || []; return tasks.length ? Math.round(tasks.filter(t => ['SUCCEEDED','FAILED','UNKNOWN','CANCELLED'].includes(t.status)).length / tasks.length * 100) : 0 })
// Poll persisted status only; preserve locally edited draft prompts until explicit confirmation.
async function load() {
  const [batches, worker] = await Promise.all([api<Batch[]>('/batches'), api<typeof executor.value>('/browser/status')])
  list.value = batches; executor.value = worker
  if (detail.value && detail.value.batch.status !== 'DRAFT') detail.value = await api<Detail>(`/batches/${detail.value.batch.id}`)
}
async function open(id: string) { detail.value = await api<Detail>(`/batches/${id}`) }
async function poll() { try { await load(); if (detail.value?.batch.status === 'ACTIVE') emit('refresh') } catch { /* Transport already presents a visible error. */ } finally { if (!stopped) timer.value = setTimeout(poll, 5000) } }
onMounted(async () => { if (props.initial) await open(props.initial.batch.id); await poll() })
onUnmounted(() => { stopped = true; clearTimeout(timer.value) })
async function confirm() {
  if (!detail.value) return
  try { await ElMessageBox.confirm(`本批次共 ${detail.value.tasks.length} 张。${detail.value.batch.mode === 'ACCOUNT' ? '将进入账号生图队列；首次使用需完成账号授权。请在账号设置中启用账号执行器。' : '测试模式不会调用 AI，输出将带测试标记。'}是否开始？`, '确认执行批次', { confirmButtonText: '确认并开始', cancelButtonText: '返回检查' }) } catch { return }
  busy.value = true
  try { await api(`/batches/${detail.value.batch.id}/confirm`, 'POST', { confirmed: true, prompts: detail.value.tasks.map(t => ({ id: t.id, prompt: t.prompt })) }); await open(detail.value.batch.id); await load() } finally { busy.value = false }
}
async function action(name: string) { if (!detail.value) return; if (name === 'cancel') { try { await ElMessageBox.confirm('仅取消尚未执行的任务，当前等待账号图片的任务会保留，可继续回填。', '取消待执行任务') } catch { return } } busy.value = true; try { await api(`/batches/${detail.value.batch.id}/${name}`, 'POST'); await open(detail.value.batch.id); await load() } finally { busy.value = false } }
const deleteReason = computed(() => {
  if (!detail.value) return ''
  if (detail.value.batch.status === 'ACTIVE') return '请先暂停或取消批次'
  if (detail.value.tasks.some(t => ['RUNNING','AWAITING_IMAGE','UNKNOWN'].includes(t.status))) return '请先处理执行中或待核实的任务'
  if (detail.value.tasks.some(t => t.outputId)) return '已有生成图片，保留任务来源记录'
  return ''
})
async function removeBatch() {
  if (!detail.value || deleteReason.value) return
  const id = detail.value.batch.id
  try { await ElMessageBox.confirm('删除此批次及其任务记录，原始参考图保留。此操作不可撤销。', '删除批次', { type: 'warning', confirmButtonText: '删除批次', cancelButtonText: '保留' }) } catch { return }
  busy.value = true
  try { await api(`/batches/${id}`, 'DELETE'); detail.value = undefined; promptTask.value = undefined; await load(); emit('refresh') } finally { busy.value = false }
}
function taskStatus(task: Task) {
  if (task.status !== 'AWAITING_IMAGE') return statusText[task.status] || task.status
  if (executor.value?.taskId === task.id && executor.value.phase === 'RUNNING') return '正在生成'
  if (executor.value?.phase === 'ERROR') return '执行器异常停止'
  if (detail.value?.batch.status !== 'ACTIVE') return '等待结果（批次已停止）'
  return executor.value?.enabled ? '等待执行器处理' : '等待启动执行器'
}
async function resolve(task: Task) { try { await ElMessageBox.confirm('仅在检查账号会话、确认该任务没有生成结果后继续。无法确认时请保留此状态，避免重复生成。', '已核实没有结果？', { confirmButtonText: '已核实没有结果', cancelButtonText: '保留待确认' }) } catch { return } await api(`/tasks/${task.id}/resolve`, 'POST', { verifiedNotAccepted: true }); await load() }
</script>
<template>
  <section class="page-heading"><div><h1>任务进度与历史</h1></div></section>
  <div class="history-layout"><div class="panel batch-picker"><label for="history-batch">批次历史 <small>{{ list.length }}</small></label><el-select id="history-batch" :model-value="detail?.batch.id" filterable placeholder="选择批次，可搜索编号、状态或日期" aria-label="选择历史批次" @change="open"><el-option v-for="b in list" :key="b.id" :value="b.id" :label="`${shortId(b.id)} · ${b.stage === 'POSE' ? '姿势底图' : '日期缺陷'} · ${statusText[b.status]} · ${new Date(b.created_at).toLocaleString()}`" /></el-select><span v-if="!list.length" class="muted">尚未创建批次</span><span v-else class="muted">共 {{ list.length }} 个批次</span></div><section v-if="detail" class="panel history-detail"><div class="panel-heading"><div><div class="eyebrow">{{ detail.batch.mode === 'TEST' ? '测试模式' : '账号生图' }}</div><h2>批次 {{ shortId(detail.batch.id) }}</h2></div><el-tag>{{ statusText[detail.batch.status] }}</el-tag></div><div class="stats"><div v-for="stat in stats" :key="stat.name"><strong>{{ stat.count }}</strong><small>{{ stat.name }}</small></div></div><el-progress :percentage="progress" :stroke-width="5" color="#1677ff" /><div class="queue-actions"><el-button v-if="detail.batch.status === 'DRAFT'" type="primary" :loading="busy" @click="confirm">确认 {{ detail.tasks.length }} 个任务并开始</el-button><el-button v-if="detail.batch.status === 'ACTIVE'" :loading="busy" @click="action('pause')">暂停后续任务</el-button><el-button v-if="detail.batch.status === 'PAUSED'" :loading="busy" @click="action('resume')">继续任务</el-button><el-button v-if="detail.tasks.some(t => t.status === 'FAILED' && t.attempts < 3)" :loading="busy" @click="action('retry')">重试失败任务</el-button><el-button v-if="detail.tasks.some(t => ['PENDING','DRAFT'].includes(t.status))" type="danger" plain :loading="busy" @click="action('cancel')">取消未执行任务</el-button><el-tooltip :content="deleteReason || '删除批次及未生成结果的任务记录'" placement="top"><span><el-button type="danger" plain :disabled="!!deleteReason" :loading="busy" @click="removeBatch">删除批次</el-button></span></el-tooltip></div><p v-if="detail.batch.status === 'DRAFT'" class="muted">请检查完整清单，可逐条预览和修改提示词。模型参数已保存于草稿快照。</p><section v-if="current" class="task-current"><b>当前任务 · {{ shortId(current.id) }} · {{ current.params.baseDate }}</b><pre>{{ current.prompt }}</pre></section><AccountTask v-for="task in detail.tasks.filter(t => ['AWAITING_IMAGE','UNKNOWN'].includes(t.status))" :key="task.id" :task="task" @completed="load(); emit('refresh')" /><el-tabs v-model="filter" class="history-tabs"><el-tab-pane label="全部" name="ALL" /><el-tab-pane label="当前" name="CURRENT" /><el-tab-pane label="已生成" name="SUCCEEDED" /><el-tab-pane label="待执行提示词" name="WAITING" /><el-tab-pane label="异常" name="FAILED" /></el-tabs><el-table class="history-table" :data="pageTasks" style="width: 100%" max-height="640"><el-table-column type="index" label="#" :index="(n: number) => (taskPage-1)*30+n+1" width="65" /><el-table-column label="生成结果" min-width="150"><template #default="{row}"><el-image v-if="row.outputId" class="task-result-thumb" :src="imageUrl(row.outputId,true)" :preview-src-list="[imageUrl(row.outputId)]" preview-teleported fit="contain" /><span v-else>—</span></template></el-table-column><el-table-column label="固定输入图" min-width="110"><template #default="{row}"><code>{{ shortId(row.inputId) }}</code></template></el-table-column><el-table-column label="生成日期" min-width="120"><template #default="{row}">{{ row.params.baseDate }}</template></el-table-column><el-table-column label="预期效果" min-width="150"><template #default="{row}">{{ row.params.defect ? defectNames[row.params.defect.type] : poseNames[row.params.pose.kind] }}<small class="block muted">{{ row.params.defect?.positions.join('、') }}</small></template></el-table-column><el-table-column label="任务状态" min-width="180"><template #default="{row}"><el-tag class="task-status-tag" :type="row.status === 'SUCCEEDED' ? 'success' : ['FAILED','UNKNOWN'].includes(row.status) ? 'danger' : 'info'">{{ taskStatus(row) }}</el-tag></template></el-table-column><el-table-column label="尝试次数" width="110" align="center"><template #default="{row}"><el-tooltip content="任务被队列领取的次数，最多 3 次；不是生图完成进度"><span>{{ row.attempts }} / 3 次</span></el-tooltip></template></el-table-column><el-table-column label="操作" min-width="150"><template #default="{row}"><el-button class="history-view" text type="primary" @click="promptTask = row">{{ detail.batch.status === 'DRAFT' ? '编辑提示词' : '查看' }} <span aria-hidden="true">›</span></el-button><el-button v-if="row.status === 'UNKNOWN'" text type="warning" @click="resolve(row)">核实受理状态</el-button><p v-if="row.error" class="error-text">{{ row.error }}</p></template></el-table-column></el-table><el-pagination class="history-pagination" background v-model:current-page="taskPage" :page-size="30" :total="filtered.length" layout="prev, pager, next, slot"><span class="muted">共 {{ filtered.length }} 条</span></el-pagination></section><div v-else class="empty-state"><h2>选择一个批次查看详情</h2><p>草稿、调用进度、失败原因和参数快照都保存在这里。</p></div></div>
  <el-dialog :model-value="!!promptTask" :title="detail?.batch.status === 'DRAFT' ? '编辑最终提示词' : '任务参数快照'" width="min(850px, 94vw)" @close="promptTask = undefined"><template v-if="promptTask"><el-input v-model="promptTask.prompt" type="textarea" :rows="17" :readonly="detail?.batch.status !== 'DRAFT'" maxlength="16000" /><pre class="metadata">{{ JSON.stringify({ parameters: promptTask.params, model: promptTask.settings, input_id: promptTask.inputId, request_id: promptTask.providerRequestId, actual_model: promptTask.actualModel, execution_channel: promptTask.executionChannel }, null, 2) }}</pre></template><template #footer><el-button type="primary" @click="promptTask = undefined">完成检查</el-button></template></el-dialog>
</template>
