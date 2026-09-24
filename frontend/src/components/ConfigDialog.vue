<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'
import { api } from '../api'
import type { Config, Settings } from '../types'
const model = defineModel<boolean>({ required: true })
const props = defineProps<{ config?: Config }>(), emit = defineEmits<{ saved: [] }>()
const form = ref<Settings>(), busy = ref(false), browserBusy = ref(false)
const browser = ref<{phase: string; message: string; enabled: boolean; taskId?: string}>()
let timer: ReturnType<typeof setTimeout>
// Poll only while the settings dialog is open; status never launches a browser.
async function pollBrowser() {
  try { browser.value = await api('/browser/status') } catch { /* Shared client displays connectivity errors. */ }
  finally { if (model.value) timer = setTimeout(pollBrowser, 5000) }
}
watch(model, value => { clearTimeout(timer); if (value) void pollBrowser() })
onUnmounted(() => clearTimeout(timer))
async function control(action: string) {
  browserBusy.value = true
  try { browser.value = await api(`/browser/${action}`, 'POST') }
  finally { browserBusy.value = false }
}
// Account preferences never collect cookies, login passwords or API credentials.
watch(() => [props.config, model.value], () => { if (props.config) form.value = { ...props.config.settings } }, { immediate: true })
async function save() { busy.value = true; try { await api('/config', 'PUT', form.value); emit('saved'); model.value = false } finally { busy.value = false } }
</script>
<template>
  <el-dialog v-model="model" title="账号生图设置" width="580px">
    <el-form v-if="form" label-position="top">
      <div class="account-login-guide"><b>ChatGPT 网页执行器</b><p>{{ browser?.message || '正在读取状态' }}</p><div class="queue-actions"><el-button :loading="browserBusy" @click="control('login')">登录 / 打开浏览器</el-button><el-button type="primary" :loading="browserBusy" :disabled="!!browser?.enabled" @click="control('start')">开始自动执行</el-button><el-button :loading="browserBusy" :disabled="!browser?.enabled" @click="control('pause')">暂停执行器</el-button></div><p class="muted">基于 chatgpt-image-batcher。首次在独立浏览器窗口登录，状态仅保存在本机。确认批次后，执行器逐张上传参考图、发送提示词、下载并保存结果，无需 Codex 逐张执行。</p><p class="muted">浏览器保持打开；登录失效、网页变化、限额或生成结果不明时会停止，需要查看浏览器处理。执行器不保证连续生成数量，不绕过账号限额。</p></div>
      <el-form-item label="期望模型（不是实际模型保证）"><el-input v-model="form.model" maxlength="120" /></el-form-item>
      <el-form-item label="画幅偏好（写入提示词，以实际输出为准）"><el-select v-model="form.size"><el-option v-for="size in ['保持参考图比例','横向照片','竖向照片','正方形照片']" :key="size" :label="size" :value="size" /></el-select></el-form-item>
      <div class="form-row"><el-form-item label="seed"><el-input disabled placeholder="账号工具未开放此参数" /></el-form-item><el-form-item label="API quality / size"><el-input disabled placeholder="账号模式不提交 API 参数" /></el-form-item></div>
      <p class="muted">日期框选范围会写入提示词。专用遮罩参数在账号模式中不保证可用；任务包附带的区域图仅作为编辑参考，不作为已经生效的遮罩或数据标注。</p>

    </el-form>
    <template #footer><el-button @click="model = false">取消</el-button><el-button type="primary" :loading="busy" @click="save">保存偏好</el-button></template>
  </el-dialog>
</template>
