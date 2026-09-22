import { useRef, useState } from 'react'
import type { Camera, Zone } from '../api'
import { zonesApi } from '../api'

type Phase = 'idle' | 'drawing'

/** Interactive polygon editor over the live MJPEG frame. Real click → point →
 * save flow; zones are normalized [0..1] so they survive resolution changes. */
export function ZoneEditor({
  camera,
  zones,
  onClose,
  onChanged,
}: {
  camera: Camera
  zones: Zone[]
  onClose: () => void
  onChanged: () => void
}) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [points, setPoints] = useState<{ x: number; y: number }[]>([])
  const [name, setName] = useState('')
  const [zoneType, setZoneType] = useState<'restricted' | 'loiter' | 'entry'>('restricted')
  const [dwell, setDwell] = useState(5)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)

  function handleCanvasClick(e: React.MouseEvent) {
    if (phase !== 'drawing') return
    const rect = wrapRef.current!.getBoundingClientRect()
    const x = (e.clientX - rect.left) / rect.width
    const y = (e.clientY - rect.top) / rect.height
    setPoints((p) => [...p, { x: +x.toFixed(4), y: +y.toFixed(4) }])
  }

  async function save() {
    setError('')
    if (points.length < 3) {
      setError('A zone needs at least 3 points.')
      return
    }
    if (!name.trim()) {
      setError('Name the zone before saving.')
      return
    }
    setSaving(true)
    try {
      await zonesApi.create({
        camera_id: camera.id,
        name: name.trim(),
        zone_type: zoneType,
        polygon: points,
        min_dwell_seconds: zoneType === 'loiter' ? dwell : 0,
        active: true,
      })
      setPhase('idle')
      setPoints([])
      setName('')
      onChanged()
    } catch (err: unknown) {
      const resp = (err as { response?: { data?: { detail?: string } } }).response
      setError(resp?.data?.detail ?? 'Save failed (needs operator role).')
    } finally {
      setSaving(false)
    }
  }

  async function removeZone(id: string) {
    await zonesApi.remove(id)
    onChanged()
  }

  async function toggleZone(z: Zone) {
    await zonesApi.update(z.id, { ...z, active: !z.active })
    onChanged()
  }

  const toPct = (v: number) => `${(v * 100).toFixed(2)}%`
  const polyStr = (pts: { x: number; y: number }[]) => pts.map((p) => `${toPct(p.x)},${toPct(p.y)}`).join(' ')

  return (
    <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-6" onClick={onClose}>
      <div className="panel max-w-5xl w-full max-h-full overflow-auto" onClick={(e) => e.stopPropagation()}>
        <div className="panel-header sticky top-0 z-10">
          <span className="panel-title">Zone Configurator — {camera.name}</span>
          <button className="btn" onClick={onClose}>
            close
          </button>
        </div>

        <div className="grid grid-cols-[1fr_300px]">
          {/* live frame + polygons */}
          <div className="p-3">
            <div
              ref={wrapRef}
              onClick={handleCanvasClick}
              className={`relative aspect-video bg-black select-none ${phase === 'drawing' ? 'cursor-crosshair' : ''}`}
            >
              <img
                src={`/api/live/mjpeg/${camera.id}?token=${encodeURIComponent(localStorage.getItem('ibvap_token') ?? '')}`}
                className="absolute inset-0 w-full h-full object-cover"
                alt="live"
              />
              <svg className="absolute inset-0 w-full h-full pointer-events-none" viewBox="0 0 100 100" preserveAspectRatio="none">
                {zones.map((z) => (
                  <polygon
                    key={z.id}
                    points={polyStr(z.polygon)}
                    fill={z.zone_type === 'restricted' ? 'rgba(255,59,48,0.18)' : z.zone_type === 'loiter' ? 'rgba(255,179,64,0.15)' : 'rgba(63,140,255,0.15)'}
                    stroke={z.zone_type === 'restricted' ? '#ff6a3d' : z.zone_type === 'loiter' ? '#ffb340' : '#3f8cff'}
                    strokeWidth="0.4"
                    opacity={z.active ? 1 : 0.35}
                  />
                ))}
                {points.length > 0 && (
                  <polygon points={polyStr(points)} fill="rgba(47,214,123,0.15)" stroke="#2fd67b" strokeWidth="0.4" strokeDasharray="1.5 1" />
                )}
                {points.map((p, i) => (
                  <circle key={i} cx={p.x * 100} cy={p.y * 100} r="0.7" fill="#2fd67b" />
                ))}
              </svg>
              {phase === 'drawing' && (
                <div className="absolute top-2 left-2 font-mono text-2xs bg-black/70 px-2 py-1 text-signal-ok">
                  CLICK TO PLACE POINTS ({points.length}) — THEN SAVE
                </div>
              )}
            </div>
            <p className="mt-2 font-mono text-2xs text-slate-500">
              Polygons are stored normalized to the frame, so they persist across resolution changes.
            </p>
          </div>

          {/* side panel */}
          <div className="border-l border-ink-700 p-3 space-y-4">
            <div>
              <div className="panel-title mb-1.5">New Zone</div>
              <input className="input w-full mb-2" placeholder="Zone name" value={name} onChange={(e) => setName(e.target.value)} />
              <div className="grid grid-cols-3 gap-1 mb-2">
                {(['restricted', 'loiter', 'entry'] as const).map((t) => (
                  <button
                    key={t}
                    className={`btn justify-center ${zoneType === t ? 'btn-primary' : ''}`}
                    onClick={() => setZoneType(t)}
                  >
                    {t}
                  </button>
                ))}
              </div>
              {zoneType === 'loiter' && (
                <label className="flex items-center gap-2 mb-2 font-mono text-2xs text-slate-400">
                  dwell ≥
                  <input
                    type="number"
                    className="input w-16"
                    min={1}
                    max={600}
                    value={dwell}
                    onChange={(e) => setDwell(+e.target.value)}
                  />
                  sec → loitering alert
                </label>
              )}
              <div className="flex gap-1.5">
                <button className="btn btn-primary flex-1 justify-center" onClick={() => setPhase(phase === 'drawing' ? 'idle' : 'drawing')}>
                  {phase === 'drawing' ? 'stop drawing' : 'draw polygon'}
                </button>
                <button className="btn flex-1 justify-center" disabled={phase !== 'drawing' || points.length < 3 || saving} onClick={save}>
                  {saving ? 'saving…' : 'save zone'}
                </button>
                <button className="btn" disabled={points.length === 0} onClick={() => setPoints([])} title="Clear current points">
                  ↺
                </button>
              </div>
              {error && <p className="mt-2 font-mono text-2xs text-red-400">{error}</p>}
            </div>

            <div>
              <div className="panel-title mb-1.5">Existing Zones ({zones.length})</div>
              <div className="space-y-1.5">
                {zones.length === 0 && <p className="font-mono text-2xs text-slate-500">No zones yet — draw one.</p>}
                {zones.map((z) => (
                  <div key={z.id} className="flex items-center justify-between bg-ink-850 border border-ink-700 rounded px-2 py-1.5">
                    <div className="min-w-0">
                      <div className="font-mono text-xs text-slate-200 truncate">{z.name}</div>
                      <div className="font-mono text-2xs text-slate-500">
                        {z.zone_type}
                        {z.zone_type === 'loiter' ? ` · ${z.min_dwell_seconds}s` : ''} · {z.polygon.length} pts
                      </div>
                    </div>
                    <div className="flex gap-1 shrink-0">
                      <button className="btn px-1.5" onClick={() => toggleZone(z)} title={z.active ? 'Deactivate zone' : 'Activate zone'}>
                        {z.active ? 'on' : 'off'}
                      </button>
                      <button className="btn btn-danger px-1.5" onClick={() => removeZone(z.id)} title="Delete zone">
                        ✕
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
