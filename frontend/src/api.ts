import axios from 'axios'

export const api = axios.create({ baseURL: '/api' })

let token: string | null = localStorage.getItem('ibvap_token')
let role: string | null = localStorage.getItem('ibvap_role')
let username: string | null = localStorage.getItem('ibvap_username')

export function setAuth(t: string, r: string, u: string) {
  token = t
  role = r
  username = u
  localStorage.setItem('ibvap_token', t)
  localStorage.setItem('ibvap_role', r)
  localStorage.setItem('ibvap_username', u)
}

export function clearAuth() {
  token = null
  role = null
  username = null
  localStorage.removeItem('ibvap_token')
  localStorage.removeItem('ibvap_role')
  localStorage.removeItem('ibvap_username')
}

export function getToken() {
  return token
}

export function getRole() {
  return role
}

export function getUsername() {
  return username
}

export function isRoleAtLeast(minimum: string) {
  const order: Record<string, number> = { viewer: 0, operator: 1, admin: 2 }
  return (order[role ?? 'viewer'] ?? -1) >= (order[minimum] ?? 99)
}

api.interceptors.request.use((cfg) => {
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401 && window.location.hash !== '#/login') {
      clearAuth()
      window.location.hash = '#/login'
    }
    return Promise.reject(err)
  },
)

// ---------- types

export interface Camera {
  id: string
  name: string
  location: string
  source: string
  fps_target: number
  notes: string
  enabled: boolean
  is_simulated: boolean
}

export interface Zone {
  id: string
  camera_id: string
  name: string
  zone_type: 'restricted' | 'loiter' | 'entry'
  polygon: { x: number; y: number }[]
  min_dwell_seconds: number
  active: boolean
}

export interface IpiDetails {
  score: number
  level: 'LOW' | 'ELEVATED' | 'HIGH' | 'CRITICAL'
  factors: {
    zone_hazard: number
    dwell_risk: number
    time_of_day: number
    target_class: number
  }
  rationale: string
}

export interface AlertItem {
  id: string
  severity: string
  status: string
  created_at: string
  acknowledged_by: string | null
  acknowledged_at: string | null
  event: {
    id: string
    kind: string
    occurred_at: string
    details: {
      zone_name?: string
      zone_type?: string
      track_key?: number
      label?: string
      dwell_s?: number
      bbox?: number[]
      clip?: string | null
      ipi?: IpiDetails | null
    } & Record<string, unknown>
    camera_id: string
    camera_name: string
    location: string
    zone_id: string | null
    snapshot_url: string | null
    clip_url: string | null
  }
}

export interface TrackInfo {
  track_id: number
  label: string
  conf: number
  bbox: number[]
}

export interface CameraRuntime {
  alive: boolean
  fps: number
  latency_ms: number
  status?: string
  error?: string | null
  recoveries?: number
  tracks?: TrackInfo[]
  frame_w?: number
  frame_h?: number
}

export interface SystemStatus {
  app: { name: string; version: string; uptime_s: number }
  python: string
  platform: string
  db: { status: string; ok: boolean }
  gpu: { cuda_available: boolean; device: string }
  cameras: Record<string, CameraRuntime>
}

// ---------- endpoints

export const authApi = {
  login: async (username: string, password: string) => {
    const { data } = await api.post('/auth/login', { username, password })
    return data as { access_token: string; role: string; username: string; display_name: string }
  },
  me: async () => {
    const { data } = await api.get('/auth/me')
    return data as { username: string; role: string; display_name: string }
  },
}

export const camerasApi = {
  list: async () => (await api.get('/cameras')).data as Camera[],
  create: async (body: Partial<Camera>) => (await api.post('/cameras', body)).data,
  update: async (id: string, body: Partial<Camera>) => (await api.patch(`/cameras/${id}`, body)).data,
  remove: async (id: string) => api.delete(`/cameras/${id}`),
  upload: async (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    const { data } = await api.post<{ filename: string; source: string }>('/cameras/upload', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },
}

export const zonesApi = {
  list: async (cameraId?: string) =>
    (await api.get('/zones', { params: cameraId ? { camera_id: cameraId } : {} })).data as Zone[],
  create: async (body: Partial<Zone>) => (await api.post('/zones', body)).data,
  update: async (id: string, body: Partial<Zone>) => (await api.patch(`/zones/${id}`, body)).data,
  remove: async (id: string) => api.delete(`/zones/${id}`),
}

export const alertsApi = {
  list: async (params: Record<string, unknown>) => (await api.get('/alerts', { params })).data as { total: number; items: AlertItem[] },
  acknowledge: async (id: string) => api.post(`/alerts/${id}/acknowledge`),
  dismiss: async (id: string) => api.post(`/alerts/${id}/dismiss`),
  auditVerify: async () =>
    (await api.get('/alerts/audit/verify')).data as {
      valid: boolean
      checked: number
      head_seq?: number
      head_hash?: string | null
      broken_at_seq?: number
      reason?: string
    },
}

export const analyticsApi = {
  summary: async () => (await api.get('/analytics/summary')).data as Record<string, number>,
  alertsOverTime: async (hours = 24, bucket = 'hour') =>
    (await api.get('/analytics/alerts_over_time', { params: { hours, bucket } })).data as { bucket: string; count: number }[],
  byKind: async () => (await api.get('/analytics/alerts_by_kind')).data as { kind: string; count: number }[],
  byCamera: async () => (await api.get('/analytics/alerts_by_camera')).data as { camera: string; count: number }[],
  byHour: async () => (await api.get('/analytics/events_by_hour')).data as { hour: number; count: number }[],
  plates: async (validOnly = false) =>
    (await api.get('/analytics/plates/recent', { params: { valid_only: validOnly, limit: 100 } })).data as {
      id: string
      text: string
      confidence: number
      is_valid_format: boolean
      seen_at: string
      camera_id: string
      snapshot: string | null
    }[],
}

export const systemApi = {
  status: async () => (await api.get('/system/status')).data as SystemStatus,
}

export function evidenceUrl(rel: string) {
  return `/api/evidence/${rel}?token=${encodeURIComponent(getToken() ?? '')}`
}

export function mjpegUrl(cameraId: string) {
  return `/api/live/mjpeg/${cameraId}?token=${encodeURIComponent(getToken() ?? '')}`
}

export function wsUrl() {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${window.location.host}/api/live/ws?token=${encodeURIComponent(getToken() ?? '')}`
}
