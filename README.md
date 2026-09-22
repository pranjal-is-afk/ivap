# IBVAP — Intelligent Border Video Analytics Platform

**Problem Statement SIH26187 · Ministry of Home Affairs / SSB**

Turn any existing IP CCTV camera into a smart sensor: real-time detection of people
and vehicles, persistent object tracking, polygon geofencing, ANPR, and instant
alerts with evidence — entirely on-premises, on commodity hardware.

This repository is a **working local prototype**: real YOLOv11n inference on GPU,
real ByteTrack tracking, real Shapely polygon zones, real EasyOCR ANPR, real
PostgreSQL persistence, real JWT+RBAC auth, and a command-center web UI.
Local video files stand in for CCTV feeds and are **labelled `SIMULATED FEED`**
in the UI; swap in `rtsp://` sources with no code changes.

## Quick start (Windows, no Docker)

```bat
:: one-time setup (see USER_MANUAL.md for the full clean-machine walkthrough)
uv venv .venv --python 3.12
uv pip install --python .venv\Scripts\python.exe -r backend\requirements.txt
uv pip install --python .venv\Scripts\python.exe torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121
:: portable Postgres: unzip assets/postgresql.zip into assets/ (assets\pgsql\bin\...)
scripts\start_ibvap.bat
```

Then open **http://localhost:5173** and log in as `admin / ibvap-admin-2026`.

Measured on the dev machine (RTX 4050 6GB): **~8 FPS per camera at the configured
target, 20–130 ms end-to-end per-frame latency, both cameras + UI + DB live
simultaneously.** The System screen shows live measured numbers — nothing is
hardcoded.

## Layout

```
backend/    FastAPI app (api/, pipeline/, services/, db/, tests/)
frontend/   React+Vite+TS command-center UI (src/App.tsx = all screens)
scripts/    start_ibvap.bat / stop_ibvap.bat / stop_pg.bat
assets/     portable postgres zip, sample videos, model cache
db/         postgres data dir (created at first run; never commit)
evidence/   alert snapshots + pre-event clips (never commit)
```

## Tests

```bat
.venv\Scripts\python.exe -m pytest backend\tests -q
```

Covers zone geometry + enter/dwell transitions, alert policy (severity, dedup,
night boost, label filtering), ANPR plate-format validation, password hashing,
JWT tampering, RBAC ordering, and hash-chain audit tamper detection.

## Honest scope notes

- **Blockchain:** implemented as a SHA-256 **hash-chained audit ledger**
  (`/api/alerts/audit/verify`), not Hyperledger — labelled as such in the UI.
- **Face recognition:** detection only (Haar). No watchlist matching; the DB
  field `matched_watchlist_id` is the hook.
- **Feeds:** recorded files = `SIMULATED FEED` badge. `rtsp://` sources run the
  identical pipeline and are labelled `RTSP`.
- Full details, limitations, and the RTSP/ONVIF swap-in guide: see **USER_MANUAL.md**.
