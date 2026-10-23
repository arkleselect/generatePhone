import { reactive } from 'vue'
import { ElMessage } from 'element-plus'
// Central transport returns actionable server messages without logging request bodies.
export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  try {
    const form = body instanceof FormData
    const response = await fetch('/api' + path, {
      method, headers: { 'X-HamLab-Request': '1', ...(!form && body !== undefined ? { 'Content-Type': 'application/json' } : {}) },
      body: body === undefined ? undefined : form ? body : JSON.stringify(body),
    })
    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: `请求失败 (${response.status})` }))
      throw new Error(error.message || '请求失败')
    }
    const text = await response.text()
    return text ? JSON.parse(text) as T : undefined as T
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '网络连接失败')
    throw error
  }
}
export const imageUrl = (id: string, thumbnail = false) => `/api/assets/${encodeURIComponent(id)}/file?thumbnail=${thumbnail}`
export const shortId = (id: string) => id.slice(0, 8).toUpperCase()
export const statusText: Record<string, string> = {
  AWAITING_IMAGE: '等待账号生图', PENDING: '待处理', APPROVED: '审核通过', REJECTED: '不通过', DRAFT: '待确认', ACTIVE: '执行中',
  PAUSED: '已暂停', CANCELLED: '已取消', COMPLETED: '已结束', RUNNING: '生成中', SUCCEEDED: '成功', FAILED: '失败', UNKNOWN: '待确认受理状态', DELETED: '审核删除',
}
// Definitions come from the shared catalog; historical task ids remain unchanged.
export const defectNames: Record<string, string> = reactive({})
export const defectDefinitions = reactive<Record<string, {label: string; datasetType: string; positions: boolean; severity: boolean; scope: 'date' | 'casing' | 'shape'}>>({})
// Casing and shape defects are generated outside the date region and need no date ROI.
export const needsDateRegion = (type: string) => (defectDefinitions[type]?.scope ?? 'date') === 'date'
export async function loadDefects() {
  const definitions = await api<typeof defectDefinitions>('/defects')
  Object.assign(defectDefinitions, definitions)
  Object.assign(defectNames, Object.fromEntries(Object.entries(definitions).map(([key,value]) => [key,value.label])))
}
export const poseNames: Record<string, string> = { original: '保持原姿势', center: '横放居中', left: '向左小幅移动', right: '向右小幅移动', up: '向上小幅移动', down: '向下小幅移动', rotate: '指定角度旋转', diagonal: '斜向摆放', vertical: '竖向摆放', custom: '自定义姿势' }

// Use the local calendar date as an editable initial value; templates always consume submitted dates.
export function initialDate() { const now = new Date(); return `${now.getFullYear()}${String(now.getMonth()+1).padStart(2,'0')}${String(now.getDate()).padStart(2,'0')}` }
