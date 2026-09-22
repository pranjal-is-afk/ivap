import { useCallback, useEffect, useRef, useState } from 'react'
import {
  alertsApi,
  analyticsApi,
  camerasApi,
  clearAuth,
  evidenceUrl,
  getRole,
  getToken,
  getUsername,
  isRoleAtLeast,
  systemApi,
  type AlertItem,
  type Camera,
  type SystemStatus,
  type Zone,
} from './api'
import { FeedTile } from './components/FeedTile'
import { ZoneEditor } from './components/ZoneEditor'
import { useLive } from './hooks/useLive'

type Screen = 'live' | 'alerts' | 'analytics' | 'system'

const SEV_COLOR: Record<string, string> = {
  critical: 'bg-alert-critical text-black',
  high: 'bg-alert-high text-black',
  medium: 'bg-alert-medium text-black',
  low: 'bg-alert-low text-white',
}

function fmtTime(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function fmtAgo(iso: string) {
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000))
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return new Date(iso).toLocaleDateString()
}

function playAlertBeep() {
  try {
    const AudioCtx =
      window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    if (!AudioCtx) return
    const ctx = new AudioCtx()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()

    osc.type = 'triangle'
    osc.frequency.setValueAtTime(880, ctx.currentTime) // High tone (A5)
    osc.frequency.setValueAtTime(659.25, ctx.currentTime + 0.12) // Low tone (E5)

    gain.gain.setValueAtTime(0.2, ctx.currentTime)
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.3)

    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.start()
    osc.stop(ctx.currentTime + 0.3)
  } catch {
    /* AudioContext requires user gesture or is muted */
  }
}

export default function App() {
  const [screen, setScreen] = useState<Screen>('live')
  const [cameras, setCameras] = useState<Camera[]>([])
  const [zones, setZones] = useState<Zone[]>([])
  const [zoneCam, setZoneCam] = useState<Camera | null>(null)
  const [system, setSystem] = useState<SystemStatus | null>(null)
  const [authed, setAuthed] = useState(!!getToken())
  const [audioAlerts, setAudioAlerts] = useState(true)
  const lastAlertIdRef = useRef<string | null>(null)
  const { alerts, plates, runtime, connected } = useLive(authed)

  const canEdit = isRoleAtLeast('operator')
  const isAdmin = getRole() === 'admin'

  // Audible operator alarm on new critical/high alerts
  useEffect(() => {
    if (!audioAlerts || alerts.length === 0) return
    const newest = alerts[0]
    if (newest && newest.id !== lastAlertIdRef.current) {
      lastAlertIdRef.current = newest.id
      if (newest.status === 'new' && (newest.severity === 'critical' || newest.severity === 'high')) {
        playAlertBeep()
      }
    }
  }, [alerts, audioAlerts])

  const refreshCameras = useCallback(async () => {
    try {
      setCameras(await camerasApi.list())
      const { zonesApi } = await import('./api')
      setZones(await zonesApi.list())
    } catch {
      /* 401 interceptor redirects */
    }
  }, [])

  useEffect(() => {
    if (!authed) return
    refreshCameras()
    const t = setInterval(refreshCameras, 10000)
    return () => clearInterval(t)
  }, [authed, refreshCameras])

  useEffect(() => {
    if (!authed) return
    const load = async () => {
      try {
        setSystem(await systemApi.status())
      } catch {
        /* noop */
      }
    }
    load()
    const t = setInterval(load, 5000)
    return () => clearInterval(t)
  }, [authed])

  if (!authed) {
    return <LoginScreen onLogin={() => setAuthed(true)} />
  }

  const openAlerts = alerts.filter((a) => a.status === 'new').length

  return (
    <div className="h-full flex flex-col">
      {/* top bar */}
      <header className="h-12 shrink-0 flex items-center px-4 gap-6 bg-ink-900 border-b border-ink-700">
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 border border-sky-800 bg-sky-950/60 rounded flex items-center justify-center">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
              <path d="M8 1l6 2.5v4c0 3.5-2.5 6-6 7.5-3.5-1.5-6-4-6-7.5v-4L8 1z" stroke="#38bdf8" strokeWidth="1.4" />
              <circle cx="8" cy="7" r="2" stroke="#38bdf8" strokeWidth="1.2" />
            </svg>
          </div>
          <div>
            <div className="font-mono text-xs tracking-[0.3em] text-slate-200">IBVAP</div>
            <div className="font-mono text-2xs text-slate-500 tracking-wider">BORDER VIDEO ANALYTICS</div>
          </div>
        </div>

        <nav className="flex gap-1 ml-4">
          {(
            [
              ['live', 'LIVE', alerts.filter((a) => a.status === 'new').length],
              ['alerts', 'ALERTS', openAlerts],
              ['analytics', 'ANALYTICS', 0],
              ['system', 'SYSTEM', 0],
            ] as [Screen, string, number][]
          ).map(([id, label, badge]) => (
            <button
              key={id}
              onClick={() => setScreen(id)}
              className={`px-3 h-8 font-mono text-2xs tracking-[0.15em] rounded border transition-colors ${
                screen === id
                  ? 'bg-ink-800 border-ink-500 text-slate-100'
                  : 'border-transparent text-slate-500 hover:text-slate-300 hover:bg-ink-850'
              }`}
            >
              {label}
              {badge > 0 ? <span className="ml-1.5 px-1 py-0.5 bg-alert-high text-black rounded text-2xs">{badge}</span> : null}
            </button>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-4">
          {/* audio alert buzzer toggle */}
          <button
            onClick={() => setAudioAlerts(!audioAlerts)}
            className={`px-2.5 h-7 font-mono text-2xs tracking-wider rounded border transition-colors flex items-center gap-1.5 ${
              audioAlerts
                ? 'bg-sky-950/60 border-sky-800 text-sky-300'
                : 'bg-ink-850 border-ink-700 text-slate-500 hover:text-slate-400'
            }`}
            title={audioAlerts ? 'Operator audible alarm enabled (tactical chime on intrusion)' : 'Audible alarm muted'}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${audioAlerts ? 'bg-sky-400 animate-pulse' : 'bg-slate-600'}`} />
            <span>{audioAlerts ? 'AUDIO ON' : 'MUTED'}</span>
          </button>

          <div className="flex items-center gap-3 font-mono text-2xs">
            <span className="flex items-center gap-1.5">
              <span className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-signal-ok' : 'bg-signal-bad'}`} />
              <span className={connected ? 'text-slate-400' : 'text-red-400'}>WS {connected ? 'LIVE' : 'DOWN'}</span>
            </span>
            <span className="text-slate-500">
              GPU {system?.gpu.cuda_available ? 'OK' : '—'}
            </span>
            <span className="text-slate-500">DB {system?.db.status ?? '…'}</span>
          </div>
          <div className="text-right">
            <div className="font-mono text-xs text-slate-300">{getUsername()}</div>
            <div className="font-mono text-2xs text-sky-400 uppercase tracking-wider">{getRole()}</div>
            {isAdmin ? <div className="font-mono text-2xs text-slate-600">admin scope</div> : null}
          </div>
          <button
            className="btn"
            onClick={() => {
              clearAuth()
              setAuthed(false)
            }}
          >
            logout
          </button>
        </div>
      </header>

      {/* body */}
      <main className="flex-1 min-h-0 overflow-hidden">
        {screen === 'live' && (
          <LiveScreen
            cameras={cameras}
            zones={zones}
            runtime={runtime}
            plates={plates}
            canEdit={canEdit}
            openZones={setZoneCam}
          />
        )}
        {screen === 'alerts' && <AlertsScreen canEdit={canEdit} />}
        {screen === 'analytics' && <AnalyticsScreen />}
        {screen === 'system' && <SystemScreen system={system} cameras={cameras} isAdmin={isAdmin} onRefreshCameras={refreshCameras} />}
      </main>

      {zoneCam && (
        <ZoneEditor
          camera={zoneCam}
          zones={zones.filter((z) => z.camera_id === zoneCam.id)}
          onClose={() => setZoneCam(null)}
          onChanged={refreshCameras}
        />
      )}
    </div>
  )
}

/* ---------------- LIVE ---------------- */

function LiveScreen({
  cameras,
  zones,
  runtime,
  plates,
  canEdit,
  openZones,
}: {
  cameras: Camera[]
  zones: Zone[]
  runtime: ReturnType<typeof useLive>['runtime']
  plates: ReturnType<typeof useLive>['plates']
  canEdit: boolean
  openZones: (c: Camera) => void
}) {
  const [showBoxes, setShowBoxes] = useState(true)
  const [focusedId, setFocusedId] = useState<string | null>(null)

  const activeCameras = focusedId ? cameras.filter((c) => c.id === focusedId) : cameras

  return (
    <div className="h-full overflow-auto p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-3">
          <span className="panel-title">Live Monitoring Grid</span>
          <label className="flex items-center gap-1.5 font-mono text-2xs text-slate-400 cursor-pointer">
            <input type="checkbox" checked={showBoxes} onChange={(e) => setShowBoxes(e.target.checked)} />
            show boxes & tracks
          </label>
          {focusedId && (
            <button
              onClick={() => setFocusedId(null)}
              className="font-mono text-2xs text-sky-400 hover:text-sky-300 underline"
            >
              ← show all {cameras.length} feeds
            </button>
          )}
        </div>
        <span className="font-mono text-2xs text-slate-500">
          {cameras.filter((c) => runtime[c.id]?.status === 'live').length}/{cameras.length} sources live · {zones.filter(z => z.active).length} geofence(s) active
        </span>
      </div>
      <div
        className="grid gap-3"
        style={{
          gridTemplateColumns: focusedId
            ? '1fr'
            : 'repeat(auto-fill, minmax(420px, 1fr))',
        }}
      >
        {activeCameras.map((c) => (
          <FeedTile
            key={c.id}
            cameraId={c.id}
            name={c.name}
            location={c.location}
            isSimulated={c.is_simulated}
            runtime={runtime[c.id]}
            zones={zones.filter((z) => z.camera_id === c.id)}
            showBoxes={showBoxes}
            canEditZones={canEdit}
            onOpenZones={() => openZones(c)}
            selected={false}
            isFocused={focusedId === c.id}
            onToggleFocus={() => setFocusedId(focusedId === c.id ? null : c.id)}
          />
        ))}
        {cameras.length === 0 && (
          <div className="panel p-8 text-center font-mono text-xs text-slate-500 col-span-full">
            No cameras configured. Add one on the SYSTEM screen.
          </div>
        )}
      </div>
      <PlateTicker plates={plates} />
    </div>
  )
}

function PlateTicker({ plates }: { plates: ReturnType<typeof useLive>['plates'] }) {
  if (plates.length === 0) return null
  return (
    <div className="panel mt-3">
      <div className="panel-header">
        <span className="panel-title">ANPR — Recent Plate Reads (live)</span>
      </div>
      <div className="p-2 flex gap-2 flex-wrap">
        {plates.slice(0, 8).map((p, i) => (
          <span
            key={`${p.ts}-${i}`}
            className={`font-mono text-xs px-2 py-1 rounded border ${
              p.is_valid ? 'border-signal-ok/40 text-signal-ok' : 'border-ink-600 text-slate-500 line-through'
            }`}
          >
            {p.text} <span className="text-slate-600">{(p.confidence * 100).toFixed(0)}%</span>
          </span>
        ))}
      </div>
    </div>
  )
}

/* ---------------- ALERTS ---------------- */

function AlertsScreen({ canEdit }: { canEdit: boolean }) {
  const [items, setItems] = useState<AlertItem[]>([])
  const [total, setTotal] = useState(0)
  const [filters, setFilters] = useState({ camera_id: '', severity: '', status: '', q: '' })
  const [selected, setSelected] = useState<AlertItem | null>(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, unknown> = { limit: 100 }
      Object.entries(filters).forEach(([k, v]) => v && (params[k] = v))
      const data = await alertsApi.list(params)
      setItems(data.items)
      setTotal(data.total)
    } finally {
      setLoading(false)
    }
  }, [filters])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    const t = setInterval(load, 8000)
    return () => clearInterval(t)
  }, [load])

  async function act(id: string, action: 'acknowledge' | 'dismiss') {
    await (action === 'acknowledge' ? alertsApi.acknowledge(id) : alertsApi.dismiss(id))
    load()
  }

  return (
    <div className="h-full flex">
      <div className="flex-1 min-w-0 flex flex-col">
        {/* filter bar */}
        <div className="flex items-center gap-2 p-2 border-b border-ink-700 bg-ink-900/60 flex-wrap">
          <select
            className="input"
            value={filters.status}
            onChange={(e) => setFilters({ ...filters, status: e.target.value })}
          >
            <option value="">any status</option>
            <option value="new">new</option>
            <option value="acknowledged">acknowledged</option>
            <option value="dismissed">dismissed</option>
          </select>
          <select
            className="input"
            value={filters.severity}
            onChange={(e) => setFilters({ ...filters, severity: e.target.value })}
          >
            <option value="">any severity</option>
            {['critical', 'high', 'medium', 'low'].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
          <input
            className="input w-56"
            placeholder="search zone / label / camera"
            value={filters.q}
            onChange={(e) => setFilters({ ...filters, q: e.target.value })}
          />
          <span className="font-mono text-2xs text-slate-500 ml-auto">
            {loading ? 'loading…' : `${items.length} of ${total}`}
          </span>
        </div>

        <div className="flex-1 overflow-auto">
          <table className="w-full font-mono text-xs">
            <thead className="sticky top-0 bg-ink-850 border-b border-ink-700">
              <tr className="text-2xs uppercase tracking-wider text-slate-500">
                <th className="text-left px-3 py-2 font-medium">Sev</th>
                <th className="text-left px-3 py-2 font-medium">IPI</th>
                <th className="text-left px-3 py-2 font-medium">Time</th>
                <th className="text-left px-3 py-2 font-medium">Kind</th>
                <th className="text-left px-3 py-2 font-medium">Camera</th>
                <th className="text-left px-3 py-2 font-medium">Zone</th>
                <th className="text-left px-3 py-2 font-medium">Label</th>
                <th className="text-left px-3 py-2 font-medium">Status</th>
                {canEdit && <th className="text-right px-3 py-2 font-medium">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {items.map((a) => (
                <tr key={a.id} className="table-row cursor-pointer" onClick={() => setSelected(a)}>
                  <td className="px-3 py-1.5">
                    <span className={`px-1.5 py-0.5 rounded text-2xs uppercase ${SEV_COLOR[a.severity] ?? 'bg-ink-700'}`}>
                      {a.severity}
                    </span>
                  </td>
                  <td className="px-3 py-1.5">
                    {a.event.details?.ipi ? (
                      <span
                        className={`px-1.5 py-0.5 rounded text-2xs font-mono font-semibold ${
                          a.event.details.ipi.level === 'CRITICAL'
                            ? 'bg-alert-critical text-black'
                            : a.event.details.ipi.level === 'HIGH'
                              ? 'bg-alert-high text-black'
                              : a.event.details.ipi.level === 'ELEVATED'
                                ? 'bg-alert-medium text-black'
                                : 'bg-ink-700 text-slate-300'
                        }`}
                        title={`IPI ${a.event.details.ipi.score}/100 — ${a.event.details.ipi.rationale}`}
                      >
                        {a.event.details.ipi.score}
                      </span>
                    ) : (
                      <span className="text-2xs text-slate-600">—</span>
                    )}
                  </td>
                  <td className="px-3 py-1.5 text-slate-400">{fmtAgo(a.created_at)}</td>
                  <td className="px-3 py-1.5 text-slate-300">{a.event.kind.replace(/_/g, ' ')}</td>
                  <td className="px-3 py-1.5 text-slate-400">{a.event.camera_name}</td>
                  <td className="px-3 py-1.5 text-slate-400">{String(a.event.details?.zone_name ?? '—')}</td>
                  <td className="px-3 py-1.5 text-slate-300">{String(a.event.details?.label ?? '—')}</td>
                  <td className="px-3 py-1.5">
                    <span
                      className={
                        a.status === 'new'
                          ? 'text-signal-warn'
                          : a.status === 'acknowledged'
                            ? 'text-signal-ok'
                            : 'text-slate-600'
                      }
                    >
                      {a.status}
                    </span>
                  </td>
                  {canEdit && (
                    <td className="px-3 py-1.5 text-right">
                      {a.status === 'new' ? (
                        <>
                          <button
                            className="btn px-1.5 py-0.5 mr-1"
                            onClick={(e) => {
                              e.stopPropagation()
                              act(a.id, 'acknowledge')
                            }}
                          >
                            ack
                          </button>
                          <button
                            className="btn btn-danger px-1.5 py-0.5"
                            onClick={(e) => {
                              e.stopPropagation()
                              act(a.id, 'dismiss')
                            }}
                          >
                            dis
                          </button>
                        </>
                      ) : (
                        <span className="text-2xs text-slate-600">{a.acknowledged_by ?? '—'}</span>
                      )}
                    </td>
                  )}
                </tr>
              ))}
              {items.length === 0 && !loading && (
                <tr>
                  <td colSpan={9} className="px-3 py-8 text-center text-slate-500">
                    No alerts match the current filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* detail drawer */}
      {selected && (
        <div className="w-[380px] shrink-0 border-l border-ink-700 bg-ink-900 overflow-auto">
          <div className="panel-header sticky top-0">
            <span className="panel-title">Alert Detail</span>
            <button className="btn" onClick={() => setSelected(null)}>
              ✕
            </button>
          </div>
          <div className="p-3 space-y-3">
            <div className="flex items-center gap-2">
              <span className={`px-2 py-0.5 rounded text-2xs uppercase ${SEV_COLOR[selected.severity] ?? 'bg-ink-700'}`}>
                {selected.severity}
              </span>
              <span className="font-mono text-2xs text-slate-500">{fmtTime(selected.created_at)}</span>
            </div>
            {selected.event.snapshot_url ? (
              <img src={evidenceUrl(selected.event.snapshot_url.replace('/api/evidence/', ''))} className="w-full rounded border border-ink-700" alt="evidence" />
            ) : (
              <div className="panel p-6 text-center font-mono text-2xs text-slate-500">no snapshot evidence</div>
            )}
            {selected.event.clip_url ? (
              <video src={evidenceUrl(selected.event.clip_url.replace('/api/evidence/', ''))} controls className="w-full rounded border border-ink-700" />
            ) : null}
            <dl className="font-mono text-2xs space-y-1">
              {[
                ['kind', selected.event.kind],
                ['camera', selected.event.camera_name],
                ['location', selected.event.location || '—'],
                ['zone', String(selected.event.details?.zone_name ?? '—')],
                ['label', String(selected.event.details?.label ?? '—')],
                ['track', String(selected.event.details?.track_key ?? '—')],
                ['dwell', selected.event.details?.dwell_s ? `${selected.event.details?.dwell_s}s` : '—'],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-3 border-b border-ink-800 pb-1">
                  <dt className="text-slate-500 uppercase tracking-wider">{k}</dt>
                  <dd className="text-slate-300 text-right truncate">{v}</dd>
                </div>
              ))}
            </dl>
            {selected.event.details?.ipi ? (
              <div className="panel p-2.5">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="panel-title">Intrusion Probability Index</span>
                  <span
                    className={`font-mono text-2xs px-1.5 py-0.5 rounded ${
                      selected.event.details.ipi.level === 'CRITICAL'
                        ? 'bg-alert-critical text-black'
                        : selected.event.details.ipi.level === 'HIGH'
                          ? 'bg-alert-high text-black'
                          : selected.event.details.ipi.level === 'ELEVATED'
                            ? 'bg-alert-medium text-black'
                            : 'bg-ink-700 text-slate-300'
                    }`}
                  >
                    {selected.event.details.ipi.level} · {selected.event.details.ipi.score}/100
                  </span>
                </div>
                <div className="space-y-1 mb-2">
                  {Object.entries(selected.event.details.ipi.factors).map(([k, v]) => (
                    <div key={k} className="flex items-center gap-2">
                      <span className="font-mono text-2xs w-24 text-slate-500 uppercase tracking-wide">{k.replace(/_/g, ' ')}</span>
                      <div className="flex-1 h-2 bg-ink-800 rounded-sm overflow-hidden">
                        <div className="h-full bg-sky-700" style={{ width: `${Math.min(100, ((v as number) / 45) * 100)}%` }} />
                      </div>
                      <span className="font-mono text-2xs w-6 text-right text-slate-400">{v as number}</span>
                    </div>
                  ))}
                </div>
                <p className="font-mono text-2xs text-slate-500 leading-relaxed">{selected.event.details.ipi.rationale}</p>
              </div>
            ) : null}
            {canEdit && selected.status === 'new' && (
              <div className="flex gap-2">
                <button className="btn btn-primary flex-1 justify-center" onClick={() => act(selected.id, 'acknowledge').then(load)}>
                  acknowledge
                </button>
                <button className="btn btn-danger flex-1 justify-center" onClick={() => act(selected.id, 'dismiss').then(load)}>
                  dismiss
                </button>
              </div>
            )}
            {selected.status !== 'new' && (
              <p className="font-mono text-2xs text-slate-500">
                {selected.status} by {selected.acknowledged_by ?? '—'} at{' '}
                {selected.acknowledged_at ? fmtTime(selected.acknowledged_at) : '—'}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

/* ---------------- ANALYTICS ---------------- */

function AnalyticsScreen() {
  const [summary, setSummary] = useState<Record<string, number> | null>(null)
  const [overTime, setOverTime] = useState<{ bucket: string; count: number }[]>([])
  const [byKind, setByKind] = useState<{ kind: string; count: number }[]>([])
  const [byCamera, setByCamera] = useState<{ camera: string; count: number }[]>([])
  const [byHour, setByHour] = useState<{ hour: number; count: number }[]>([])
  const [plates, setPlates] = useState<ReturnType<typeof analyticsApi.plates> extends Promise<infer R> ? R : never>([])

  useEffect(() => {
    const load = async () => {
      setSummary(await analyticsApi.summary())
      setOverTime(await analyticsApi.alertsOverTime(24, 'hour'))
      setByKind(await analyticsApi.byKind())
      setByCamera(await analyticsApi.byCamera())
      setByHour(await analyticsApi.byHour())
      setPlates(await analyticsApi.plates())
    }
    load()
    const t = setInterval(load, 15000)
    return () => clearInterval(t)
  }, [])

  const maxCount = Math.max(1, ...overTime.map((d) => d.count))
  const maxHour = Math.max(1, ...byHour.map((d) => d.count))

  return (
    <div className="h-full overflow-auto p-3 space-y-3">
      {/* KPI strip */}
      <div className="grid grid-cols-4 lg:grid-cols-8 gap-2">
        {summary &&
          (
            [
              ['alerts 24h', summary.alerts_24h],
              ['open', summary.open_alerts],
              ['total alerts', summary.total_alerts],
              ['events', summary.events],
              ['tracks', summary.tracks],
              ['cameras', summary.cameras],
              ['plates', summary.plates],
              ['faces', summary.faces],
            ] as [string, number][]
          ).map(([label, value]) => (
            <div key={label} className="panel px-3 py-2">
              <div className="font-mono text-2xs uppercase tracking-wider text-slate-500">{label}</div>
              <div className="font-mono text-xl text-slate-100">{value}</div>
            </div>
          ))}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">Alerts — last 24h (hourly)</span>
          </div>
          <div className="p-3">
            <div className="flex items-end gap-0.5 h-28">
              {overTime.length === 0 && <span className="font-mono text-2xs text-slate-500">no alerts in window</span>}
              {overTime.map((d) => (
                <div key={d.bucket} className="flex-1 h-full flex items-end group relative" title={`${d.bucket}: ${d.count}`}>
                  <div
                    className="w-full bg-sky-800 group-hover:bg-sky-600 rounded-t"
                    style={{ height: `${Math.max(d.count / maxCount * 100, d.count > 0 ? 3 : 0)}%` }}
                  />
                </div>
              ))}
            </div>
            <div className="flex justify-between font-mono text-2xs text-slate-600 mt-1">
              <span>24h ago</span>
              <span>now</span>
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">Events by local hour</span>
          </div>
          <div className="p-3">
            <div className="flex items-end gap-0.5 h-28">
              {byHour.length === 0 && <span className="font-mono text-2xs text-slate-500">no events yet</span>}
              {byHour.map((d) => (
                <div key={d.hour} className="flex-1 h-full flex flex-col items-center justify-end" title={`${d.hour}:00 — ${d.count} events`}>
                  <div
                    className="w-full bg-amber-700/70 rounded-t"
                    style={{ height: `${Math.max(d.count / maxHour * 100, d.count > 0 ? 3 : 0)}%` }}
                  />
                  {d.hour % 6 === 0 ? (
                    <div className="font-mono text-2xs text-slate-600 mt-0.5">{d.hour}</div>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">Alerts by kind</span>
          </div>
          <div className="p-3 space-y-1.5">
            {byKind.length === 0 && <span className="font-mono text-2xs text-slate-500">no data</span>}
            {byKind.map((d) => (
              <div key={d.kind} className="flex items-center gap-2">
                <span className="font-mono text-2xs w-36 text-slate-400">{d.kind.replace(/_/g, ' ')}</span>
                <div className="flex-1 h-3 bg-ink-800 rounded-sm overflow-hidden">
                  <div
                    className="h-full bg-sky-700"
                    style={{ width: `${(d.count / Math.max(...byKind.map((x) => x.count))) * 100}%` }}
                  />
                </div>
                <span className="font-mono text-2xs w-8 text-right text-slate-300">{d.count}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">Alerts by camera</span>
          </div>
          <div className="p-3 space-y-1.5">
            {byCamera.length === 0 && <span className="font-mono text-2xs text-slate-500">no data</span>}
            {byCamera.map((d) => (
              <div key={d.camera} className="flex items-center gap-2">
                <span className="font-mono text-2xs w-36 truncate text-slate-400">{d.camera}</span>
                <div className="flex-1 h-3 bg-ink-800 rounded-sm overflow-hidden">
                  <div
                    className="h-full bg-emerald-800"
                    style={{ width: `${(d.count / Math.max(...byCamera.map((x) => x.count))) * 100}%` }}
                  />
                </div>
                <span className="font-mono text-2xs w-8 text-right text-slate-300">{d.count}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* plates table */}
      <div className="panel">
        <div className="panel-header">
          <span className="panel-title">ANPR — Plate reads</span>
        </div>
        <div className="overflow-auto max-h-64">
          <table className="w-full font-mono text-xs">
            <thead className="sticky top-0 bg-ink-850">
              <tr className="text-2xs uppercase text-slate-500">
                <th className="text-left px-3 py-1.5">Plate</th>
                <th className="text-left px-3 py-1.5">Conf</th>
                <th className="text-left px-3 py-1.5">Valid</th>
                <th className="text-left px-3 py-1.5">Time</th>
              </tr>
            </thead>
            <tbody>
              {plates.map((p) => (
                <tr key={p.id} className="table-row">
                  <td className="px-3 py-1 text-slate-200">{p.text}</td>
                  <td className="px-3 py-1 text-slate-400">{(p.confidence * 100).toFixed(0)}%</td>
                  <td className="px-3 py-1">
                    <span className={p.is_valid_format ? 'text-signal-ok' : 'text-slate-600'}>
                      {p.is_valid_format ? 'HSRP-ish' : 'no'}
                    </span>
                  </td>
                  <td className="px-3 py-1 text-slate-500">{fmtAgo(p.seen_at)}</td>
                </tr>
              ))}
              {plates.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-3 py-6 text-center text-slate-500">
                    No plate reads yet — ANPR runs when vehicles are detected.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

/* ---------------- SYSTEM ---------------- */

function AddCameraModal({
  onClose,
  onAdded,
}: {
  onClose: () => void
  onAdded: () => void
}) {
  const [name, setName] = useState('')
  const [location, setLocation] = useState('')
  const [sourceType, setSourceType] = useState<'sample' | 'webcam' | 'rtsp' | 'upload'>('sample')
  const [samplePath, setSamplePath] = useState('assets/videos/border_patrol.mp4')
  const [webcamIndex, setWebcamIndex] = useState('0')
  const [rtspUrl, setRtspUrl] = useState('')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [fpsTarget, setFpsTarget] = useState(10)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) {
      setError('Camera name is required')
      return
    }
    setBusy(true)
    setError('')
    try {
      let finalSource = ''
      if (sourceType === 'sample') {
        finalSource = samplePath
      } else if (sourceType === 'webcam') {
        finalSource = webcamIndex
      } else if (sourceType === 'rtsp') {
        if (!rtspUrl.trim()) {
          throw new Error('RTSP URL is required')
        }
        finalSource = rtspUrl.trim()
      } else if (sourceType === 'upload') {
        if (!selectedFile) {
          throw new Error('Please select a video file to upload')
        }
        const uploaded = await camerasApi.upload(selectedFile)
        finalSource = uploaded.source
      }

      await camerasApi.create({
        name: name.trim(),
        location: location.trim(),
        source: finalSource,
        fps_target: fpsTarget,
        enabled: true,
      })
      onAdded()
      onClose()
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string }
      setError(e.response?.data?.detail || e.message || 'Failed to add camera')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4 backdrop-blur-xs">
      <div className="panel w-full max-w-md border border-ink-600 bg-ink-900 shadow-2xl">
        <div className="panel-header flex justify-between items-center bg-ink-850 px-4 py-3 border-b border-ink-700">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-sky-500 animate-pulse" />
            <span className="panel-title text-slate-100 font-mono text-xs tracking-wider">ADD SURVEILLANCE FEED</span>
          </div>
          <button type="button" onClick={onClose} className="btn hover:bg-ink-700 px-2 py-1 text-slate-400">
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-4 space-y-4 font-mono text-xs">
          {error && (
            <div className="p-2.5 rounded bg-red-950/60 border border-red-800 text-red-300 text-2xs">
              {error}
            </div>
          )}

          <div className="space-y-1">
            <label className="text-2xs uppercase tracking-wider text-slate-400">Camera Name</label>
            <input
              className="input w-full"
              placeholder="e.g. Sector 4 East Outpost"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>

          <div className="space-y-1">
            <label className="text-2xs uppercase tracking-wider text-slate-400">Tactical Location</label>
            <input
              className="input w-full"
              placeholder="e.g. Pillar 82/4 - Perimeter Wire"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
            />
          </div>

          <div className="space-y-1">
            <label className="text-2xs uppercase tracking-wider text-slate-400">Stream Source Type</label>
            <div className="grid grid-cols-2 gap-1.5 pt-1">
              {[
                { id: 'sample', label: 'Local Asset' },
                { id: 'webcam', label: 'USB/DirectShow' },
                { id: 'rtsp', label: 'RTSP Stream' },
                { id: 'upload', label: 'Upload Video' },
              ].map((t) => (
                <button
                  type="button"
                  key={t.id}
                  onClick={() => setSourceType(t.id as 'sample' | 'webcam' | 'rtsp' | 'upload')}
                  className={`px-2.5 py-2 rounded text-2xs text-left border transition-colors ${
                    sourceType === t.id
                      ? 'bg-sky-950 border-sky-600 text-sky-200'
                      : 'bg-ink-800 border-ink-700 text-slate-400 hover:border-ink-600'
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          {sourceType === 'sample' && (
            <div className="space-y-1">
              <label className="text-2xs uppercase tracking-wider text-slate-400">Select Video Asset</label>
              <select
                className="input w-full"
                value={samplePath}
                onChange={(e) => setSamplePath(e.target.value)}
              >
                <option value="assets/videos/border_patrol.mp4">border_patrol.mp4 (Daylight Patrol)</option>
                <option value="assets/videos/border_patrol_night.mp4">border_patrol_night.mp4 (Night / Low-Light)</option>
                <option value="assets/videos/sample_patrol.mp4">sample_patrol.mp4 (Checkpoint / Vehicles)</option>
              </select>
            </div>
          )}

          {sourceType === 'webcam' && (
            <div className="space-y-1">
              <label className="text-2xs uppercase tracking-wider text-slate-400">DirectShow Device Index</label>
              <input
                className="input w-full"
                placeholder="0 for default camera, 1 for external USB"
                value={webcamIndex}
                onChange={(e) => setWebcamIndex(e.target.value)}
              />
              <p className="text-2xs text-slate-500">Uses native Windows DirectShow (cv2.CAP_DSHOW) without driver latency.</p>
            </div>
          )}

          {sourceType === 'rtsp' && (
            <div className="space-y-1">
              <label className="text-2xs uppercase tracking-wider text-slate-400">RTSP Stream URI</label>
              <input
                className="input w-full"
                placeholder="rtsp://admin:password@192.168.1.100:554/live"
                value={rtspUrl}
                onChange={(e) => setRtspUrl(e.target.value)}
              />
              <p className="text-2xs text-slate-500">Supports ONVIF Profile T streams with automatic reconnect.</p>
            </div>
          )}

          {sourceType === 'upload' && (
            <div className="space-y-1">
              <label className="text-2xs uppercase tracking-wider text-slate-400">Upload Video File (.mp4 / .avi)</label>
              <input
                type="file"
                accept="video/mp4,video/avi"
                className="input w-full text-slate-400 file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:text-2xs file:bg-sky-900 file:text-sky-200 hover:file:bg-sky-800"
                onChange={(e) => setSelectedFile(e.target.files?.[0] ?? null)}
              />
              <p className="text-2xs text-slate-500">Video is stored on server and looped as continuous surveillance feed.</p>
            </div>
          )}

          <div className="space-y-1">
            <div className="flex justify-between items-center">
              <label className="text-2xs uppercase tracking-wider text-slate-400">Inference Target FPS</label>
              <span className="text-2xs text-sky-400 font-semibold">{fpsTarget} FPS</span>
            </div>
            <input
              type="range"
              min={5}
              max={25}
              step={1}
              value={fpsTarget}
              onChange={(e) => setFpsTarget(Number(e.target.value))}
              className="w-full accent-sky-500 bg-ink-800"
            />
            <div className="flex justify-between text-2xs text-slate-500">
              <span>5 FPS (Power Save)</span>
              <span>10 FPS (Optimal RTX 4050)</span>
              <span>25 FPS (Max)</span>
            </div>
          </div>

          <div className="flex gap-2 pt-2">
            <button
              type="button"
              className="btn flex-1 justify-center py-2"
              onClick={onClose}
              disabled={busy}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-primary flex-1 justify-center py-2 text-sky-200"
              disabled={busy}
            >
              {busy ? 'CONNECTING FEED…' : 'INITIALIZE FEED'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function AuditLedgerCard() {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<{
    valid: boolean
    checked: number
    head_seq?: number
    head_hash?: string | null
    broken_at_seq?: number
    reason?: string
    verifiedAt?: string
  } | null>(null)
  const [error, setError] = useState('')

  async function verifyLedger() {
    setLoading(true)
    setError('')
    try {
      const data = await alertsApi.auditVerify()
      setResult({ ...data, verifiedAt: new Date().toLocaleTimeString() })
    } catch (e: unknown) {
      const err = e as { message?: string }
      setError(err.message || 'Audit verification failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="panel">
      <div className="panel-header flex items-center justify-between">
        <div className="flex items-center gap-2">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-sky-400">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            <path d="M9 12l2 2 4-4" />
          </svg>
          <span className="panel-title">Cryptographic Audit Ledger (SHA-256 Chain)</span>
        </div>
        <button
          className="btn btn-primary text-2xs px-2.5 py-1"
          disabled={loading}
          onClick={verifyLedger}
        >
          {loading ? 'VERIFYING HASHES…' : 'VERIFY LEDGER INTEGRITY'}
        </button>
      </div>
      <div className="p-3 space-y-3 font-mono text-xs">
        {error && (
          <div className="p-2 rounded bg-red-950/60 border border-red-800 text-red-300 text-2xs">
            {error}
          </div>
        )}

        {result ? (
          <div className="space-y-2">
            <div className="flex items-center justify-between p-2 rounded bg-ink-850 border border-ink-700">
              <div className="flex items-center gap-2">
                <span
                  className={`w-2.5 h-2.5 rounded-full ${
                    result.valid ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]' : 'bg-red-500'
                  }`}
                />
                <span className="text-2xs font-semibold uppercase tracking-wider text-slate-200">
                  {result.valid ? 'LEDGER INTEGRITY VERIFIED (TAMPER-FREE)' : `INTEGRITY CHECK FAILED (SEQ #${result.broken_at_seq})`}
                </span>
              </div>
              <span className="text-2xs text-slate-400">Checked at {result.verifiedAt}</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
              <div className="bg-ink-850 p-2 rounded border border-ink-800">
                <div className="text-2xs uppercase text-slate-500">Verified Blocks</div>
                <div className="text-lg font-bold text-slate-100">{result.checked} entries</div>
              </div>
              <div className="bg-ink-850 p-2 rounded border border-ink-800 md:col-span-2">
                <div className="text-2xs uppercase text-slate-500">Head Block Hash (Seq #{result.head_seq ?? '—'})</div>
                <div className="text-2xs text-sky-400 truncate select-all font-mono" title={result.head_hash ?? 'None'}>
                  {result.head_hash ?? '—'}
                </div>
              </div>
            </div>

            <div className="text-2xs text-slate-400 bg-ink-850/50 p-2 rounded border border-ink-800">
              <span className="text-slate-500 uppercase">Verification Status:</span>{' '}
              {result.valid ? (
                <span className="text-emerald-400">All {result.checked} cryptographic block links validated successfully without discrepancies.</span>
              ) : (
                <span className="text-red-400">Broken at block #{result.broken_at_seq}: {result.reason}</span>
              )}
            </div>
          </div>
        ) : (
          <div className="p-3 bg-ink-850/50 rounded border border-ink-800 text-slate-400 text-2xs flex items-center justify-between">
            <span>Audit chain is active. Click 'Verify Ledger Integrity' to validate cryptographic hash sequence.</span>
            <span className="text-slate-500">SHA-256 HASH-CHAINED</span>
          </div>
        )}

        <div className="text-2xs text-slate-500 leading-relaxed border-t border-ink-800/80 pt-2">
          Every alert emission, operator acknowledgment, and dismissal calculates <code className="text-slate-400">SHA256(prev_hash + entry_id + payload_bytes)</code>. This immutable chronological hash sequence prevents post-hoc tampering of border incident logs. Built for drop-in interoperability with permissioned Hyperledger Fabric / BSF Consortium chaincode.
        </div>
      </div>
    </div>
  )
}

function SystemScreen({
  system,
  cameras,
  isAdmin,
  onRefreshCameras,
}: {
  system: SystemStatus | null
  cameras: Camera[]
  isAdmin: boolean
  onRefreshCameras?: () => void
}) {
  const [showAddModal, setShowAddModal] = useState(false)

  return (
    <div className="h-full overflow-auto p-3 space-y-3">
      {showAddModal && (
        <AddCameraModal
          onClose={() => setShowAddModal(false)}
          onAdded={() => {
            onRefreshCameras?.()
          }}
        />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">Platform</span>
            <span className="font-mono text-2xs text-slate-500">v{system?.app.version}</span>
          </div>
          <div className="p-3 font-mono text-xs space-y-1.5">
            {[
              ['gpu device', system?.gpu.device ?? '…'],
              ['cuda', system?.gpu.cuda_available ? 'available' : 'unavailable'],
              ['database', system?.db.status],
              ['python', system?.python],
              ['uptime', system ? `${Math.floor(system.app.uptime_s / 60)}m ${system.app.uptime_s % 60}s` : '…'],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between border-b border-ink-800 pb-1">
                <span className="text-slate-500 uppercase text-2xs tracking-wider">{k}</span>
                <span className="text-slate-300">{v}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">Cameras</span>
            <button
              className="btn btn-primary"
              disabled={!isAdmin}
              onClick={() => setShowAddModal(true)}
              title={isAdmin ? 'Add a new surveillance source' : 'Requires admin role'}
            >
              + add camera
            </button>
          </div>
          <div className="p-3 space-y-2">
            {cameras.map((c) => (
              <div key={c.id} className="flex items-center justify-between bg-ink-850 border border-ink-700 rounded px-2.5 py-2">
                <div className="min-w-0">
                  <div className="font-mono text-xs text-slate-200">{c.name}</div>
                  <div className="font-mono text-2xs text-slate-500 truncate">{c.source}</div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {c.is_simulated ? (
                    <span className="font-mono text-2xs px-1.5 py-0.5 bg-amber-500/90 text-black rounded font-medium">SIM</span>
                  ) : (
                    <span className="font-mono text-2xs px-1.5 py-0.5 bg-sky-800 text-sky-300 rounded font-medium">LIVE</span>
                  )}
                  <button
                    className="btn btn-danger"
                    disabled={!isAdmin}
                    onClick={async () => {
                      if (confirm(`Delete camera ${c.name}?`)) {
                        await camerasApi.remove(c.id)
                        onRefreshCameras?.()
                      }
                    }}
                  >
                    del
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Cryptographic Audit Ledger card */}
      <AuditLedgerCard />

      <div className="panel">
        <div className="panel-header">
          <span className="panel-title">Measured pipeline performance (real, from running threads)</span>
        </div>
        <div className="overflow-auto">
          <table className="w-full font-mono text-xs">
            <thead className="bg-ink-850">
              <tr className="text-2xs uppercase text-slate-500">
                <th className="text-left px-3 py-1.5">Camera</th>
                <th className="text-left px-3 py-1.5">Thread</th>
                <th className="text-left px-3 py-1.5">FPS</th>
                <th className="text-left px-3 py-1.5">Latency</th>
                <th className="text-left px-3 py-1.5">Recoveries</th>
                <th className="text-left px-3 py-1.5">Status</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(system?.cameras ?? {}).map(([cid, rt]) => (
                <tr key={cid} className="table-row">
                  <td className="px-3 py-1.5 text-slate-300">{cameras.find((c) => c.id === cid)?.name ?? cid}</td>
                  <td className="px-3 py-1.5">{rt.alive ? <span className="text-signal-ok">alive</span> : <span className="text-red-400">dead</span>}</td>
                  <td className="px-3 py-1.5">{rt.fps.toFixed(1)}</td>
                  <td className="px-3 py-1.5">{rt.latency_ms.toFixed(0)} ms</td>
                  <td className="px-3 py-1.5">{rt.recoveries ?? 0}</td>
                  <td className="px-3 py-1.5 text-slate-400">{rt.status}{rt.error ? ` — ${rt.error}` : ''}</td>
                </tr>
              ))}
              {!system && (
                <tr>
                  <td colSpan={6} className="px-3 py-6 text-center text-slate-500">
                    loading…
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel p-3 font-mono text-2xs text-slate-500 leading-relaxed">
        <span className="text-slate-400 uppercase tracking-wider">Prototype scope notes — honest labels:</span>
        <br />• Feeds from local files are real pipelines over recorded video, marked SIMULATED FEED. RTSP / Webcam sources show as LIVE.
        <br />• Blockchain audit trail is implemented as a SHA-256 hash-chained ledger (verify endpoint under /api/alerts/audit/verify) — with clean interface for Hyperledger Fabric.
        <br />• Face recognition/watchlist matching is not implemented; face detection only. ONVIF Profile T discovery interface in backend/app/pipeline/ingest.py is ready for network cameras.
      </div>
    </div>
  )
}

/* ---------------- LOGIN ---------------- */

function LoginScreen({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const { authApi, setAuth } = await import('./api')
      const res = await authApi.login(username, password)
      setAuth(res.access_token, res.role, res.username)
      onLogin()
    } catch {
      setError('Invalid credentials')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="h-full flex items-center justify-center">
      <form onSubmit={submit} className="panel w-96 p-6 space-y-4">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 border border-sky-800 bg-sky-950/60 rounded flex items-center justify-center">
            <svg width="18" height="18" viewBox="0 0 16 16" fill="none">
              <path d="M8 1l6 2.5v4c0 3.5-2.5 6-6 7.5-3.5-1.5-6-4-6-7.5v-4L8 1z" stroke="#38bdf8" strokeWidth="1.4" />
              <circle cx="8" cy="7" r="2" stroke="#38bdf8" strokeWidth="1.2" />
            </svg>
          </div>
          <div>
            <div className="font-mono text-sm tracking-[0.3em] text-slate-200">IBVAP</div>
            <div className="font-mono text-2xs text-slate-500">BORDER VIDEO ANALYTICS PLATFORM</div>
          </div>
        </div>
        <div className="space-y-2">
          <input className="input w-full" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="username" />
          <input className="input w-full" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="password" />
        </div>
        {error && <div className="font-mono text-2xs text-red-400">{error}</div>}
        <button className="btn btn-primary w-full justify-center h-9" disabled={busy}>
          {busy ? 'authenticating…' : 'AUTHENTICATE'}
        </button>
        <div className="font-mono text-2xs text-slate-600 leading-relaxed">
          Roles: admin / operator / viewer — seeded creds in USER_MANUAL.md
        </div>
      </form>
    </div>
  )
}
