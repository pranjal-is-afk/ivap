"""Live monitoring: MJPEG stream per camera + WebSocket alert/track push."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user
from app.services.ws_manager import ws_manager

router = APIRouter(prefix="/live", tags=["live"])


@router.get("/mjpeg/{camera_id}")
def mjpeg(camera_id: str, token: str = ""):
    """MJPEG live stream. Token comes via query param because <img> tags
    cannot set Authorization headers. Auth is still enforced."""
    from app.api.deps import get_current_user
    from app.core.security import decode_token
    from app.db.models import User
    from app.db.session import SessionLocal
    from app.main import worker

    if token:
        try:
            payload = decode_token(token)
        except Exception:
            raise HTTPException(status_code=401, detail="invalid token")
        db = SessionLocal()
        try:
            user = db.get(User, payload.get("sub"))
            if user is None or not user.is_active:
                raise HTTPException(status_code=401, detail="invalid user")
        finally:
            db.close()
    else:
        raise HTTPException(status_code=401, detail="token required")

    if camera_id not in worker.workers:
        raise HTTPException(status_code=404, detail="camera not running")

    q = worker.register_mjpeg(camera_id)

    async def gen():
        try:
            while camera_id in worker.workers:
                try:
                    jpeg = await asyncio.to_thread(q.get, True, 5.0)
                except Exception:
                    continue  # timeout: check loop condition, send keepalive
                yield (
                    b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                    + str(len(jpeg)).encode()
                    + b"\r\n\r\n" + jpeg + b"\r\n"
                )
        finally:
            worker.unregister_mjpeg(camera_id, q)

    return StreamingResponse(
        gen(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store"},
    )


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    """Push channel: alerts, plate reads, track updates. Requires ?token=JWT."""
    from app.core.security import decode_token

    token = websocket.query_params.get("token", "")
    try:
        payload = decode_token(token)
    except Exception:
        await websocket.close(code=4401)
        return

    await ws_manager.connect(websocket)
    sender = asyncio.create_task(ws_manager.sender_loop(websocket))
    try:
        while True:
            # client pings keep the socket honest; we ignore contents
            msg = await websocket.receive_text()
            if msg == "ping":
                await ws_manager.broadcast({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        sender.cancel()
        ws_manager.disconnect(websocket)
