// Shared HTTP contracts keep image ancestry and requested/confirmed labels distinct.
export interface Roi { x: number; y: number; width: number; height: number }
export interface Pose { kind: string; angle: number; shift: number; description: string }
export interface Defect { type: string; positions: number[]; severity: string; part: string; direction: string; object: string; description: string }
export interface Settings { provider: string; baseUrl: string; model: string; size: string; quality: string; timeoutSeconds: number }
export interface Asset {
  id: string; rootSourceId: string; parentPoseId: string | null; role: string; sourceType: string; filename: string
  width: number; height: number; fileSize: number; baseDate: string; pose: Pose; roi: Roi | null; review: string
  label: string | null; quality: string | null; rejectionReason: string | null; taskId: string | null; createdAt: string
}
export interface Task {
  id: string; batchId: string; inputId: string; rootSourceId: string; status: string
  params: { baseDate: string; pose: Pose; defect: Defect | null; roi: Roi | null; randomization?: { dateMode: string; startDate: string; endDate: string; format: string; maxAffected: number } | null }
  prompt: string; settings: Settings; attempts: number; error: string | null; outputId: string | null
  providerRequestId: string | null; actualModel: string | null; executionChannel: string | null; createdAt: string
}
export interface Batch { id: string; stage: string; status: string; mode: string; created_at: string }
export interface Detail { batch: Batch; tasks: Task[] }
export interface Config { settings: Settings; executionMode: string; maskSupported: boolean; seedSupported: boolean }
