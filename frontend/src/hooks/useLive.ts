import { useEffect, useRef, useState } from 'react'
import type { AlertItem, CameraRuntime, TrackInfo } from '../api'
import { wsUrl } from '../api'

export interface LiveAlert extends AlertItem {
  /** true when it arrived over WS after page load */
  fresh?: boolean
}

export interface PlateRead {
  type: 'plate'
  camera_id: string
  camera_name: string
  text: string
  confidence: number
  is_valid: boolean
  snapshot_url?: string | null
  ts: number
}

export type WsMessage =
  | { type: 'alert'; [k: string]: unknown }
  | { type: 'plate'; [k: string]: unknown }
  | { type: 'tracks'; camera_id: string; [k: string]: unknown }
  | { type: 'pong' }

/** Single shared WebSocket feeding alerts, plates and per-camera track states.
 *  Reconnects when `authed` flips (token only exists after login). */
export function useLive(authed: boolean) {
  const [alerts, setAlerts] = useState<LiveAlert[]>([])
  const [plates, setPlates] = useState<PlateRead[]>([])
  const [runtime, setRuntime] = useState<Record<string, CameraRuntime>>({})
  const [connected, setConnected] = useState(false)
  const socketRef = useRef<WebSocket | null>(null)
  const backoffRef = useRef(1000)

  useEffect(() => {
    let closed = false
    let timer: ReturnType<typeof setTimeout>

    function connect() {
      const ws = new WebSocket(wsUrl())
      socketRef.current = ws

      ws.onopen = () => {
        setConnected(true)
        backoffRef.current = 1000
      }
      ws.onmessage = (ev) => {
        let msg: WsMessage
        try {
          msg = JSON.parse(ev.data)
        } catch {
          return
        }
        if (msg.type === 'alert') {
          // Alert pushed by the pipeline in its wire format — re-shape minimally
          const a = msg as unknown as AlertItem
          setAlerts((prev) => [a, ...prev].slice(0, 200))
        } else if (msg.type === 'plate') {
          setPlates((prev) => [msg as unknown as PlateRead, ...prev].slice(0, 50))
        } else if (msg.type === 'tracks') {
          const { camera_id, ...rest } = msg as { camera_id: string } & Record<string, unknown>
          setRuntime((prev) => ({
            ...prev,
            [camera_id]: {
              alive: rest.status === 'live',
              fps: rest.fps as number,
              latency_ms: rest.latency_ms as number,
              status: rest.status as string,
              error: rest.error as string | null,
              recoveries: rest.recoveries as number,
              tracks: rest.tracks as TrackInfo[],
              frame_w: rest.frame_w as number,
              frame_h: rest.frame_h as number,
            },
          }))
        }
      }
      ws.onclose = () => {
        setConnected(false)
        if (!closed) {
          timer = setTimeout(connect, backoffRef.current)
          backoffRef.current = Math.min(backoffRef.current * 2, 15000)
        }
      }
      ws.onerror = () => ws.close()
    }

    if (authed) connect()
    return () => {
      closed = true
      clearTimeout(timer)
      socketRef.current?.close()
    }
  }, [authed])

  function pushAlertFromHttp(a: AlertItem) {
    setAlerts((prev) => [a, ...prev].slice(0, 200))
  }

  return { alerts, setAlerts, plates, runtime, connected, pushAlertFromHttp }
}
