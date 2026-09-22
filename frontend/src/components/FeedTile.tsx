import { useEffect, useRef } from 'react'
import type { CameraRuntime, Zone } from '../api'
import { mjpegUrl } from '../api'

const LABEL_COLORS: Record<string, string> = {
  person: '#2fd67b',
  car: '#38bdf8',
  truck: '#38bdf8',
  bus: '#38bdf8',
  motorcycle: '#38bdf8',
  bicycle: '#38bdf8',
}

/** One live feed tile: MJPEG <img> + canvas overlay for real geofences + boxes/IDs. */
export function FeedTile({
  cameraId,
  name,
  location,
  isSimulated,
  runtime,
  zones = [],
  showBoxes,
  onOpenZones,
  canEditZones,
  selected,
  isFocused = false,
  onToggleFocus,
}: {
  cameraId: string
  name: string
  location: string
  isSimulated: boolean
  runtime?: CameraRuntime
  zones?: Zone[]
  showBoxes: boolean
  onOpenZones?: () => void
  canEditZones: boolean
  selected?: boolean
  isFocused?: boolean
  onToggleFocus?: () => void
}) {
  const imgRef = useRef<HTMLImageElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const runtimeRef = useRef<CameraRuntime | undefined>(runtime)
  runtimeRef.current = runtime
  const showBoxesRef = useRef(showBoxes)
  showBoxesRef.current = showBoxes
  const zonesRef = useRef<Zone[]>(zones)
  zonesRef.current = zones

  // Redraw overlay whenever runtime updates (via parent re-render on WS push)
  useEffect(() => {
    const canvas = canvasRef.current
    const img = imgRef.current
    if (!canvas || !img) return
    const w = img.clientWidth
    const h = img.clientHeight
    if (!w || !h) return
    canvas.width = w
    canvas.height = h
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.clearRect(0, 0, w, h)

    // 1. Draw active zone geofences
    const currentZones = zonesRef.current
    if (currentZones && currentZones.length > 0) {
      for (const z of currentZones) {
        if (!z.active || !z.polygon || z.polygon.length < 3) continue
        const zcolor = z.zone_type === 'restricted' ? '#ef4444' : z.zone_type === 'loiter' ? '#f59e0b' : '#06b6d4'
        const zfill =
          z.zone_type === 'restricted'
            ? 'rgba(239, 68, 68, 0.14)'
            : z.zone_type === 'loiter'
              ? 'rgba(245, 158, 11, 0.14)'
              : 'rgba(6, 182, 212, 0.14)'

        ctx.beginPath()
        z.polygon.forEach((pt, idx) => {
          const px = pt.x * w
          const py = pt.y * h
          if (idx === 0) ctx.moveTo(px, py)
          else ctx.lineTo(px, py)
        })
        ctx.closePath()
        ctx.fillStyle = zfill
        ctx.fill()
        ctx.strokeStyle = zcolor
        ctx.lineWidth = 1.5
        ctx.setLineDash([5, 3])
        ctx.stroke()
        ctx.setLineDash([])

        // Zone label tag
        const first = z.polygon[0]
        ctx.font = '9px "IBM Plex Mono", monospace'
        const tag = `${z.name} [${z.zone_type.toUpperCase()}]`
        const tw = ctx.measureText(tag).width
        const tagX = Math.min(Math.max(first.x * w, 4), w - tw - 10)
        const tagY = Math.min(Math.max(first.y * h, 14), h - 6)
        ctx.fillStyle = 'rgba(7, 17, 11, 0.85)'
        ctx.fillRect(tagX, tagY - 11, tw + 8, 13)
        ctx.strokeStyle = zcolor
        ctx.lineWidth = 1
        ctx.strokeRect(tagX, tagY - 11, tw + 8, 13)
        ctx.fillStyle = zcolor
        ctx.fillText(tag, tagX + 4, tagY - 1)
      }
    }

    // 2. Draw detections and persistent track IDs
    const rt = runtimeRef.current
    if (!showBoxesRef.current) return
    if (!rt || !rt.tracks || !rt.frame_w || !rt.frame_h) return
    const sx = w / rt.frame_w
    const sy = h / rt.frame_h
    for (const t of rt.tracks) {
      const [x1, y1, x2, y2] = t.bbox
      const color = LABEL_COLORS[t.label] ?? '#e2e8f0'
      ctx.strokeStyle = color
      ctx.lineWidth = 1.5
      ctx.strokeRect(x1 * sx, y1 * sy, (x2 - x1) * sx, (y2 - y1) * sy)
      const label = `${t.label} #${t.track_id}`
      ctx.font = '10px "IBM Plex Mono", monospace'
      const tw = ctx.measureText(label).width
      const ly = Math.max(y1 * sy - 14, 0)
      ctx.fillStyle = color
      ctx.fillRect(x1 * sx, ly, tw + 8, 13)
      ctx.fillStyle = '#07110b'
      ctx.fillText(label, x1 * sx + 4, ly + 10)
    }
  }, [runtime, zones])

  const live = runtime?.status === 'live' && runtime?.alive

  return (
    <div
      className={`panel overflow-hidden relative group transition-all duration-200 ${
        selected ? 'ring-1 ring-sky-700' : ''
      } ${isFocused ? 'col-span-full ring-2 ring-sky-500' : ''}`}
      data-camera-tile
    >
      {/* header strip */}
      <div className="flex items-center justify-between px-2.5 h-8 bg-ink-850 border-b border-ink-700">
        <div className="flex items-center gap-2 min-w-0">
          <span
            className={`w-1.5 h-1.5 rounded-full ${live ? 'bg-signal-ok animate-pulse' : 'bg-signal-bad'}`}
          />
          <span className="font-mono text-2xs uppercase tracking-wider text-slate-300 truncate">
            {name}
          </span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {runtime?.fps ? (
            <span className="font-mono text-2xs text-slate-500">{runtime.fps.toFixed(1)} fps</span>
          ) : null}
          {onToggleFocus ? (
            <button
              onClick={onToggleFocus}
              className="font-mono text-2xs text-slate-400 hover:text-slate-200 uppercase tracking-wider"
              title={isFocused ? 'Exit focus view' : 'Focus this feed'}
            >
              {isFocused ? 'minimize' : 'focus'}
            </button>
          ) : null}
          {canEditZones && onOpenZones ? (
            <button
              onClick={onOpenZones}
              className="font-mono text-2xs text-sky-400 hover:text-sky-300 uppercase tracking-wider"
              title="Configure virtual fence / zones"
            >
              zones ({zones.length})
            </button>
          ) : null}
        </div>
      </div>

      {/* video area (fixed 16:9, image object-cover) */}
      <div className={`relative bg-black ${isFocused ? 'aspect-[16/9] max-h-[65vh]' : 'aspect-video'}`}>
        <img
          ref={imgRef}
          src={mjpegUrl(cameraId)}
          className="absolute inset-0 w-full h-full object-cover"
          alt={`${name} feed`}
          onError={(e) => {
            ;(e.target as HTMLImageElement).style.opacity = '0.15'
          }}
        />
        <canvas ref={canvasRef} className="absolute inset-0 w-full h-full pointer-events-none" />

        {isSimulated ? (
          <span className="absolute top-2 left-2 font-mono text-2xs px-1.5 py-0.5 bg-amber-500/90 text-black font-semibold tracking-wider">
            SIMULATED FEED
          </span>
        ) : (
          <span className="absolute top-2 left-2 font-mono text-2xs px-1.5 py-0.5 bg-sky-950/80 text-sky-300 border border-sky-800/70 font-semibold tracking-wider">
            RTSP LIVE
          </span>
        )}
        {runtime === undefined ? (
          <span className="absolute top-2 right-2 font-mono text-2xs px-1.5 py-0.5 bg-black/60 text-slate-400 rounded">
            CONNECTING…
          </span>
        ) : !live ? (
          <div className="absolute inset-0 flex items-center justify-center bg-black/70">
            <span className="font-mono text-xs text-red-400 uppercase tracking-widest">
              {runtime?.error ? 'SOURCE ERROR' : 'OFFLINE'}
            </span>
          </div>
        ) : null}
      </div>

      {/* footer: location + telemetry */}
      <div className="flex items-center justify-between px-2.5 h-7 bg-ink-900 border-t border-ink-800">
        <span className="font-mono text-2xs text-slate-500 truncate">{location || '—'}</span>
        <span className="font-mono text-2xs text-slate-400">
          {runtime?.tracks?.length ?? 0} trk · {runtime?.latency_ms?.toFixed(0) ?? '—'} ms · {zones.filter(z => z.active).length} fence(s)
        </span>
      </div>
    </div>
  )
}

