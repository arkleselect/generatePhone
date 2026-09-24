<script setup lang="ts">
import { computed, ref, watch, onUnmounted } from 'vue'
import { initialDate, api, defectNames, defectDefinitions, imageUrl, poseNames, shortId } from '../api'
import type { Asset, Defect, Detail, Pose } from '../types'
const props = defineProps<{ assets: Asset[] }>(), emit = defineEmits<{ created: [Detail] }>()
const stage = ref('DEFECT'), mode = ref('ACCOUNT'), date = ref(initialDate()), selected = ref<string[]>([]), count = ref(1), busy = ref(false)
const poses = ref<Pose[]>([{ kind: 'original', angle: 10, shift: 5, description: '' }])
// Random dates and damage are resolved by the backend for each image and frozen in its task snapshot.
const coverageMode = ref('ALL'), randomDates = ref(0), estimated = ref(0), estimating = ref(false)
const dateMode = ref('RANDOM'), dateFormat = ref('yyyyMMdd')
const range = ref<[string,string]>([`${new Date().getFullYear()-3}-01-01`, `${new Date().getFullYear()}-${String(new Date().getMonth()+1).padStart(2,'0')}-${String(new Date().getDate()).padStart(2,'0')}`])
function defectConfig(type: string): Defect { return { type, positions: [], severity: '随机', part: '随机', direction: '随机', object: '随机', description: '' } }
const defects = ref<Defect[]>(['missing_chars'].map(defectConfig))
const choice = ref('missing_chars'), severity = ref('随机'), part = ref('随机'), direction = ref('随机'), object = ref('随机'), description = ref('')
const positionTypes = computed(() => Object.keys(defectDefinitions).filter(key => defectDefinitions[key]?.positions))
const severityTypes = computed(() => Object.keys(defectDefinitions).filter(key => defectDefinitions[key]?.severity))
const candidates = computed(() => props.assets.filter(a => stage.value === 'POSE' ? a.role === 'SOURCE' : a.role === 'POSE' && a.review === 'APPROVED' && a.roi).filter(a => mode.value === 'TEST' || a.sourceType !== 'TEST'))
const total = computed(() => estimated.value)
// Send the same payload for server-side quantity estimation and final preview expansion.
function payload() { return { stage: stage.value, mode: mode.value, inputIds: selected.value, baseDate: date.value, count: count.value, poses: poses.value, defects: defects.value,
  randomization: { dateMode: stage.value === 'DEFECT' && coverageMode.value !== 'RANDOM' ? 'FIXED' : dateMode.value, startDate: range.value?.[0], endDate: range.value?.[1], format: dateFormat.value, maxAffected: 8 },
  coverage: stage.value === 'DEFECT' ? { positions: coverageMode.value, randomDates: randomDates.value } : null } }
let estimateTimer: ReturnType<typeof setTimeout>, revision = 0
watch(payload, () => {
  const current = ++revision; estimated.value = 0; clearTimeout(estimateTimer)
  if (!selected.value.length) { estimating.value = false; return }
  estimating.value = true
  estimateTimer = setTimeout(async () => {
    try { const result = await api<{ total: number }>('/plans/estimate', 'POST', payload()); if (revision === current) estimated.value = result.total }
    catch { /* Invalid configuration is displayed by the shared client. */ }
    finally { if (revision === current) estimating.value = false }
  }, 600)
}, { deep: true })
onUnmounted(() => { revision++; clearTimeout(estimateTimer) })
watch([stage, mode], () => { selected.value = [] })
function toggle(id: string) { selected.value = selected.value.includes(id) ? selected.value.filter(v => v !== id) : [...selected.value, id] }
function addDefect() { defects.value.push({ type: choice.value, positions: [], severity: severityTypes.value.includes(choice.value) ? severity.value : '', part: part.value, direction: direction.value, object: object.value, description: description.value }) }
// Add each built-in class once for convenient, evenly represented training batches.
function addAll() { for (const type of Object.keys(defectNames).filter(t => t !== 'custom')) if (!defects.value.some(d => d.type === type)) defects.value.push(defectConfig(type)) }
async function draft() {
  busy.value = true
  try { emit('created', await api<Detail>('/batches', 'POST', payload())) }
  finally { busy.value = false }
}
</script>
<template>
  <section class="page-heading"><div><h1>创建批量任务</h1></div></section>
  <div class="builder-layout"><div class="builder-main">
    <section class="panel"><div class="panel-heading"><b>选择工作阶段</b></div><el-radio-group v-model="stage"><el-radio-button value="POSE">阶段 A · 生成正常姿势</el-radio-button><el-radio-button value="DEFECT">阶段 B · 生成日期缺陷</el-radio-button></el-radio-group><p class="muted">{{ stage === 'POSE' ? '以真实原图为参考，生成完整正常日期和不同姿势。' : '仅显示已审核且已框选日期区域的底图；日期会按本次配置替换，不要求与底图日期相同。' }}</p><div v-if="!candidates.length" class="inline-empty">暂无可用图片，请先上传并完成底图审核与日期框选。</div><div class="select-grid"><button v-for="a in candidates" :key="a.id" :class="['select-image', { selected: selected.includes(a.id) }]" @click="toggle(a.id)"><img :src="imageUrl(a.id, true)" alt="选择参考图片"><span>{{ shortId(a.id) }} <b>{{ selected.includes(a.id) ? '✓' : '+' }}</b></span><small>{{ a.baseDate }}{{ a.sourceType === 'TEST' ? ' · 测试' : '' }}</small></button></div></section>
    <section class="panel"><div class="panel-heading"><b>{{ stage === 'POSE' ? '姿势参数' : '日期与缺陷' }}</b></div><el-form label-position="top"><!-- Date controls apply to both normal pose generation and defect datasets. -->
      <template v-if="stage === 'DEFECT'"><el-form-item label="位置覆盖方式"><el-select v-model="coverageMode"><el-option value="ALL" label="全部位置组合（8位日期255种）" /><el-option value="CONTIGUOUS" label="连续位置组合（8位日期36种）" /><el-option value="RANDOM" label="随机采样" /></el-select></el-form-item>
      <template v-if="coverageMode !== 'RANDOM'"><el-form-item label="先完整覆盖此日期"><el-input v-model="date" maxlength="10" /></el-form-item><el-form-item label="再追加多少个随机日期（逐个完整覆盖）"><el-input-number v-model="randomDates" :min="0" :max="100" /></el-form-item><p class="muted">同一个数字出现在不同位置会分别覆盖；每个位置组合重复次数见右侧。程度、方向等按配置采样，并非穷举所有外观。</p></template></template>
      <el-form-item v-if="stage === 'POSE' || coverageMode === 'RANDOM'" label="生产日期"><el-radio-group v-model="dateMode"><el-radio-button value="RANDOM">每张随机日期</el-radio-button><el-radio-button value="FIXED">指定日期</el-radio-button></el-radio-group></el-form-item>
      <div v-if="(stage === 'DEFECT' && coverageMode !== 'RANDOM') || dateMode === 'RANDOM'" class="form-row"><el-form-item label="随机日期范围"><el-date-picker v-model="range" type="daterange" value-format="YYYY-MM-DD" start-placeholder="开始日期" end-placeholder="结束日期" :clearable="false" style="width:100%;min-width:0" /></el-form-item><el-form-item label="日期格式"><el-select v-model="dateFormat"><el-option label="年月日 · 不带分隔符" value="yyyyMMdd" /><el-option label="年月日 · 横线分隔" value="yyyy-MM-dd" /><el-option label="年月日 · 点号分隔" value="yyyy.MM.dd" /></el-select></el-form-item></div>
      <el-form-item v-else label="指定的完整日期"><el-input v-model="date" maxlength="32" placeholder="输入完整日期" /></el-form-item>
      <template v-if="stage === 'POSE'"><div v-for="(pose, index) in poses" :key="index" class="variant-row"><div class="form-row"><el-form-item label="姿势"><el-select v-model="pose.kind"><el-option v-for="(name, key) in poseNames" :key="key" :value="key" :label="name" /></el-select></el-form-item><el-form-item v-if="['rotate','diagonal'].includes(pose.kind)" label="角度（正顺时针 / 负逆时针）"><el-input-number v-model="pose.angle" :min="-180" :max="180" /></el-form-item><el-form-item v-if="['left','right','up','down'].includes(pose.kind)" label="位移（画面尺寸 %）"><el-input-number v-model="pose.shift" :min="0" :max="25" /></el-form-item></div><el-input v-model="pose.description" :placeholder="pose.kind === 'custom' ? '填写自定义姿势（必填）' : '补充说明（可选）'" maxlength="1000" /><el-button text type="danger" @click="poses.splice(index, 1)">移除此姿势</el-button></div><el-button @click="poses.push({ kind: 'rotate', angle: 10, shift: 5, description: '' })">＋ 添加姿势</el-button></template>
      <template v-else><div class="form-row"><el-form-item label="主要缺陷"><el-select v-model="choice"><el-option v-for="(name, key) in defectNames" :key="key" :label="name" :value="key" /></el-select></el-form-item><el-form-item v-if="severityTypes.includes(choice)" label="程度"><el-radio-group v-model="severity"><el-radio-button v-for="level in ['随机','轻度','中度','重度']" :key="level" :value="level">{{ level }}</el-radio-button></el-radio-group></el-form-item></div>
      <p class="muted">按所选方式自动覆盖数字位置；多字符掉点至少影响两个数字，无需逐位勾选。</p>
      <el-form-item v-if="choice === 'partial_break'" label="断码部位"><el-select v-model="part"><el-option v-for="p in ['随机','上部','下部','左侧','右侧','局部笔画']" :key="p" :value="p" /></el-select></el-form-item><el-form-item v-if="['smear','double_print'].includes(choice)" label="方向"><el-radio-group v-model="direction"><el-radio v-for="d in ['随机','左','右','上','下']" :key="d" :value="d">{{ d }}</el-radio></el-radio-group></el-form-item><el-form-item v-if="choice === 'occlusion'" label="遮挡物种类（填写“随机”可自动变化）"><el-input v-model="object" maxlength="200" /></el-form-item><el-form-item :label="choice === 'custom' ? '自定义缺陷名称与说明（必填）' : '补充说明（可选）'"><el-input v-model="description" type="textarea" maxlength="1000" :rows="2" /></el-form-item><el-button @click="addDefect">＋ 加入缺陷配置清单</el-button><el-button @click="addAll">加入全部常用类型</el-button>
      <div class="variant-list"><div v-for="(d, i) in defects" :key="i"><b>{{ String(i+1).padStart(2,'0') }}</b><span>{{ defectNames[d.type] }} <small>{{ positionTypes.includes(d.type) ? '按覆盖方式展开' : '' }} {{ severityTypes.includes(d.type) ? (d.severity === '随机' ? '· 程度随机' : '· '+d.severity) : '' }}</small></span><el-button text type="danger" @click="defects.splice(i,1)">移除</el-button></div></div></template>
    </el-form></section>
  </div><aside class="batch-summary panel"><h2>本次任务</h2><div class="summary-line"><span>输入图片</span><b>{{ selected.length }}</b></div><div class="summary-line"><span>{{ stage === 'POSE' ? '姿势配置' : '缺陷配置' }}</span><b>{{ stage === 'POSE' ? poses.length : defects.length }}</b></div><el-form label-position="top"><el-form-item  :label="stage === 'DEFECT' && coverageMode !== 'RANDOM' ? '每个位置组合重复张数' : '每张底图 × 每类缺陷的张数'"><el-input-number v-model="count" :min="1" :max="5000" /></el-form-item><el-form-item label="执行模式"><el-select v-model="mode"><el-option label="测试模式 · 不调用 AI" value="TEST" /><el-option label="账号生图 · 使用已授权账号" value="ACCOUNT" /></el-select></el-form-item></el-form><div class="call-total"><strong>{{ total }}</strong><span>{{ mode === 'TEST' ? '个测试任务 / 0 次 API 调用' : '次账号生图任务' }}</span></div><p class="muted">默认并发 1。随机日期与缺陷会在预览时确定，确认后才开始执行。</p><el-alert v-if="mode === 'TEST'" title="测试图片仅用于验证流程，不能导出为数据集。" type="warning" :closable="false" /><el-alert v-else title="确认后等待账号生图。请在账号设置中连接账号执行器。" type="info" :closable="false" /><el-button class="full-width" type="primary" size="large" :disabled="total < 1 || total > 5000 || estimating" :loading="busy" @click="draft">预览 {{ total }} 个任务 →</el-button><small class="muted">每批最多 5000 张</small></aside></div>
</template>
