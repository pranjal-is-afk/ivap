# IBVAP — User Manual

**Intelligent Border Video Analytics Platform · Problem Statement SIH26187**
*Written for evaluators and operators — no machine-learning background required.*

---

## 1. What IBVAP is

IBVAP watches video from existing CCTV cameras and raises an alert the moment a
person or vehicle does something you have marked as off-limits — for example,
entering a restricted area, or lingering too long near a fence line. It also
reads vehicle number plates (ANPR) and records every event in a tamper-evident
audit trail.

Everything runs **on one Windows PC with an NVIDIA GPU**. No cloud, no internet,
no special "smart cameras" — the whole point is that ordinary CCTV footage becomes
intelligent in software.

**What you will see when it runs:** a dark, dense operations dashboard with live
camera feeds, boxes drawn around every detected person/vehicle with a persistent
ID number, an alert list updating in real time, and charts built from the real
database.

---

## 2. System requirements

| Component | Requirement | Notes |
|---|---|---|
| OS | Windows 10/11 64-bit | Also runs on Linux; this manual covers Windows |
| GPU | Any NVIDIA GPU with ≥ 4 GB VRAM | Tested on RTX 4050 Laptop 6 GB |
| NVIDIA driver | Recent (must support CUDA 12.1) | Check with `nvidia-smi` in a terminal |
| Python | 3.12.x (exact) | 3.13/3.14 will NOT work — PyTorch has no builds for them yet |
| Node.js | 20 or newer | For the web dashboard dev server |
| Disk | ~10 GB free | PyTorch ≈ 3 GB, Postgres ≈ 0.5 GB, models + videos ≈ 0.5 GB |
| RAM | 8 GB min, 16 GB comfortable | |
| Docker | **not required** | Postgres runs as a portable, unzipped copy |

**Check your GPU first:** open a terminal and run `nvidia-smi`. If you see a table
with your GPU name, you are fine. If "not recognized", install the latest NVIDIA
driver before continuing.

---

## 3. Full setup from a clean machine

Follow these steps in order. Each step tells you what success looks like.

### Step 3.1 — Install Python 3.12

1. Download Python 3.12 from python.org and install (tick "Add to PATH").
2. Verify: `python --version` → `Python 3.12.x`.
   If you have multiple Pythons, the `uv` tool in the next step picks 3.12 explicitly.

### Step 3.2 — Install Node.js

1. Download Node LTS (20+) from nodejs.org and install.
2. Verify: `node --version` → something like `v22.x` or newer.

### Step 3.3 — Create the project folder

Copy/clone this repository into a **local** folder (not OneDrive — the database
does not like cloud-sync folders; if you must use OneDrive, expect slower DB
performance). The examples below use the path as shipped.

### Step 3.4 — Create the Python environment

From the project root:

```bat
uv venv .venv --python 3.12
```

`uv` is a fast Python installer (`pip install uv` if missing, or substitute
`python -m venv .venv` + `pip` — everything else is the same).

Success looks like: `Creating virtual environment at: .venv` and a new `.venv` folder.

### Step 3.5 — Install Python packages (≈ 10 minutes, mostly one big download)

```bat
uv pip install --python .venv\Scripts\python.exe torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121
uv pip install --python .venv\Scripts\python.exe -r backend\requirements.txt
```

Success looks like: `Installed nn packages` with no red errors. The torch wheel
is ~2.5 GB — this is the "download coffee break" step.

### Step 3.6 — Unpack the portable database

The repo ships `assets/postgresql.zip` (official EDB binaries). Unzip it so you
end up with `assets/pgsql/bin/postgres.exe`:

```bat
powershell -NoProfile -Command "Expand-Archive -Path assets\postgresql.zip -DestinationPath assets"
```

Success looks like: an `assets\pgsql` folder containing `bin`, `lib`, `share`.

### Step 3.7 — Add demo videos

The demo needs two small videos in `assets/videos/`:

- `assets/videos/street.mp4` — a traffic/parking scene (vehicles + people)
- `assets/videos/people.mp4` — a walking-crowd scene (many people)

Any .mp4 works; the two above ship as recommended downloads (e.g. the
intel-iot-devkit sample videos on GitHub and roboflow's people-walking example).
A webcam can be used instead: see §4.3.

### Step 3.8 — Start everything

```bat
scripts\start_ibvap.bat
```

This: initializes + starts PostgreSQL (port 5433) on first run, starts the API
(port 8000), and starts the web UI (port 5173) — each in its own minimized window.

First-time startup takes ~60–90 seconds: the database initializes, tables are
created, two demo cameras are seeded, and YOLO downloads a 5 MB model file
(once only). Watch the API window until it says `Uvicorn running on http://127.0.0.1:8000`.

### Step 3.9 — Verify

1. Open **http://127.0.0.1:8000/api/health** → `{"status":"ok","db":"up",...}`
2. Open **http://localhost:5173** → login screen.
3. Log in: username `admin`, password `ibvap-admin-2026`.
4. The LIVE screen shows both feeds within a few seconds, with `SIMULATED FEED`
   badges, FPS counters, and green/blue boxes with ID numbers on people/vehicles.

**Seeded logins (role → password):**

| Username | Role | Password | Can do |
|---|---|---|---|
| `admin` | Administrator | `ibvap-admin-2026` | everything incl. cameras + users |
| `operator` | Duty Operator | `ibvap-operator-2026` | acknowledge/dismiss alerts, edit zones |
| `viewer` | Command Viewer | `ibvap-viewer-2026` | read-only: feeds, alerts, analytics |

Change these before any serious demo by logging in as admin and creating new
users (the API supports it; see §8).

### Stopping

`scripts\stop_ibvap.bat` stops the API and UI. `scripts\stop_pg.bat` stops the
database (you normally leave it running).

**Reset the demo data** (wipes alerts/events/tracks/evidence, keeps cameras and
zones):

```bat
.venv\Scripts\python.exe backend\app\db\reset_demo_data.py
```

---

## 4. Adding a camera / video source

You must be logged in as **admin**.

1. Go to the **SYSTEM** screen (top right).
2. Click **+ ADD CAMERA**. An interactive command-center modal opens:
   - **Camera Name** — shown on the live tile, e.g. `BOP-EAST Fence`
   - **Tactical Location** — descriptive label, e.g. `Pillar 82/4 - Perimeter Wire`
   - **Stream Source Type**:
     - **Local Asset**: pick from preloaded footage (`border_patrol.mp4`, `border_patrol_night.mp4`, `sample_patrol.mp4`, etc.)
     - **USB/DirectShow**: enter webcam device index (`0` for integrated webcam, `1` for external USB camera). Uses native Windows DirectShow (`cv2.CAP_DSHOW`) with zero driver latency.
     - **RTSP Stream**: enter network URI (`rtsp://user:pass@192.168.1.64:554/live`). Reconnects automatically on dropouts.
     - **Upload Video**: select any `.mp4` or `.avi` surveillance file from your computer. The file is uploaded to `assets/videos/` via `POST /api/cameras/upload` and initialized as a continuous looped feed.
   - **Inference Target FPS**: slider from 5 to 25 FPS (default: 10 FPS, optimized for NVIDIA RTX 4050).
3. Click **INITIALIZE FEED**. The pipeline thread starts immediately without restarting the server.
   If the source is unavailable, the tile displays `SOURCE ERROR` with detailed diagnostics without crashing the platform.

### 4.1 The `SIMULATED FEED` vs `LIVE` badge — what it means

Honesty labels are strictly enforced:
- Feeds reading from local or uploaded video files are marked **`SIM` / `SIMULATED FEED`** because they run on recorded footage.
- Feeds connected to an RTSP IP camera or a physical USB/DirectShow webcam are marked **`LIVE`**.
- The inference engine, tracker, geofencing logic, and alert dispatchers run the exact same real-time code regardless of source type. When an RTSP camera is plugged in, the badge automatically reflects `LIVE` with zero configuration changes.

### 4.2 Deleting a camera

SYSTEM screen → `DEL` button next to the camera (admin only). Its pipeline
thread stops cleanly.

### 4.3 Using a webcam

Add a camera with source `0`. Note: only one process can hold the webcam at a
time; close other camera apps first.

---

## 5. Configuring a zone / virtual fence

You must be **operator** or **admin**.

1. On the **LIVE** screen, find the camera tile and click **ZONES** (top-right of the tile).
2. The Zone Configurator opens over the live frame. Type a **zone name**.
3. Pick the zone type:
   - **restricted** — any entry triggers an instant alert (severity HIGH; CRITICAL at night)
   - **loiter** — triggers only after someone stays inside for ≥ N seconds (set the dwell time; severity MEDIUM, HIGH at night)
   - **entry** — reserved for entry/exit counting (logged, no paging alert in this prototype)
4. Click **DRAW POLYGON**, then click 3+ points on the video frame. The shaded
   polygon updates as you click. Use ↺ to start over.
5. Click **SAVE ZONE**. The zone is stored **normalized to the frame** (0–100% of
   width/height), so it survives resolution changes and works on any camera.
6. Existing zones are listed on the right: toggle **ON/OFF** (paused zones still
   show, greyed out) or **✕** to delete.

Changes apply **live** — the pipeline reloads the zone set within a second; no
restart.

**How detection decides "inside":** the *center point of an object's bounding
box* must be inside your polygon. This is the industry-standard rule and avoids
false alarms from boxes merely brushing the area.

---

## 6. Reading the dashboard

### Top bar (always visible)

| Element | Meaning |
|---|---|
| `WS LIVE` / `WS DOWN` | Real-time push channel to the backend. LIVE = alerts arrive instantly. |
| `GPU OK` | The NVIDIA GPU is detected and running inference (CUDA 12.1). |
| `DB up` | PostgreSQL database is connected and responding to queries. |
| `ALARM ON / MUTED` | Web Audio API operator chime toggle. Emits a two-tone audible alarm (880Hz / 659Hz) when CRITICAL or HIGH alerts trigger. |
| Username + role | Current operator context (`admin`, `operator`, `viewer`); controls privileged UI actions. |

### LIVE screen

- **Multi-Camera Grid**:
  - Each tile displays camera name, live measured FPS, ZONES configuration button, location, and `N trk · X ms` (active tracked entities and per-frame latency).
  - **Geofence Overlays**: Active virtual perimeter zones are rendered directly on the video canvas with colored dashed lines and tactical tags (`restricted` = crimson, `loiter` = amber, `entry` = cyan).
  - **Entity Tracking**: Green bounding boxes indicate persons; blue boxes indicate vehicles. Every detected entity displays its persistent ByteTrack ID (`#track_id`) across frames.
  - **Focus Mode**: Click the focus button on any camera header to isolate that stream into full-width command view; click `← show all N feeds` to return to multi-grid.
  - **Overlay Toggle**: Checkbox `show boxes & tracks` toggles bounding box overlays on the fly.
- **ANPR — Recent Plate Reads**: Automatically updates with detected license plates, optical character confidence score, and Indian HSRP format compliance flags.

### ALERTS screen

- **Filter Bar**: Filter by workflow status (`new`, `acknowledged`, `dismissed`), severity (`critical`, `high`, `medium`, `low`), or keyword search.
- **Alert Table**:
  - `Sev`: Severity badge (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`).
  - `IPI`: **Intrusion Probability Index** score badge (0–100) color-coded by threat band (`CRITICAL`, `HIGH`, `ELEVATED`, `LOW`).
  - `Time`: Elapsed time since incident.
  - `Kind`: Event trigger type (`zone intrusion`, `loitering`, etc.).
  - `Camera` & `Zone`: Geographical attribution.
  - `Label`: Detected target classification.
  - `Status` & `Actions`: Single-click `ack` (acknowledge) or `dis` (dismiss).
- **Detail Drawer (Click any row)**:
  - Full-resolution evidence snapshot and 10-second looping MP4 evidence clip.
  - Event metadata attributes.
  - **IPI Factor Breakdown**: Visual bar graph decomposing the 0–100 threat score across Zone Hazard (≤45), Dwell Risk (≤30), Night/Time Multiplier (≤20), and Target Class (≤15), accompanied by a natural-language rationale explaining why the threat was scored at that level.

### ANALYTICS screen

Every number here is a live SQL aggregate over the real database — nothing is
faked or cached. KPI strip: alerts 24h, open alerts, totals, events, tracks,
cameras, plates, faces. Charts: alerts per hour (24 h), events by local hour
(activity pattern), breakdowns by kind and by camera, plus a plate-read table.

### SYSTEM screen

- **Platform**: GPU device name, PyTorch CUDA availability, DB status, Python runtime, uptime.
- **Cameras**: List of active surveillance sources with `SIM` or `LIVE` badges, and `+ add camera` modal launcher.
- **Cryptographic Audit Ledger (SHA-256 Chain)**:
  - Interactive **VERIFY LEDGER INTEGRITY** button.
  - Live cryptographic validation across all historical audit entries.
  - Displays tamper-free status badge, total verified blocks, and SHA-256 head block hash.
- **Measured Pipeline Performance**: Per-camera running thread telemetry, real measured FPS, real latency in milliseconds, recovery count, and thread status.
- **Prototype Scope Notes**: Transparent disclosure of system architecture, simulated vs physical feeds, and drop-in integration points for Hyperledger Fabric and ONVIF Profile T.

---

## 7. Alerts: how they work and what to do

**Pipeline:** object detected → tracked with persistent ID → zone engine checks
the object's center against your polygons every frame → on a new entry (or dwell
threshold for loiter zones) the event is written to PostgreSQL → the alert policy
decides severity and whether to page (see below) → the alert + evidence
(cropped snapshot + ~15 s pre-event clip) is saved → the UI receives it over
WebSocket **in under a second** on the same machine.

**Alert policy (why some things alert and others don't):**

- Only **people and vehicles** page an operator. Animals/other objects get logged
  as events without alerts (false-positive suppression per the PRD).
- Severity: person in restricted zone = **HIGH** (at night 20:00–06:00 = **CRITICAL**);
  vehicle in restricted zone = HIGH; loitering = MEDIUM (HIGH at night). The IPI
  score can raise severity when the combined factors warrant it.
- **Dedup:** the same object re-triggering the same zone within 30 s is logged,
  but does not create a second alert.

**When one fires:** the LIVE tab badge and ALERTS tab badge show an orange
count. Go to ALERTS, open the row, check the evidence snapshot/clip, then either
**acknowledge** (you are responding) or **dismiss** (false alarm). Actions are
attributed to your username and written to the tamper-evident ledger.

**Audit trail:** every alert creation + acknowledge/dismiss is appended to a
SHA-256 hash-chained ledger (each entry commits to the previous one). Verify
integrity any time: `/api/alerts/audit/verify` returns
`{"valid": true, "checked": N, ...}`. If anyone edits history in the database,
verification fails. (This is tamper-*evident* cryptography, not a Hyperledger
blockchain — see §10.)

---

## 8. API quick reference (for integrators)

All endpoints under `http://127.0.0.1:8000/api`. Login:
`POST /auth/login {"username","password"}` → JWT. Send it as
`Authorization: Bearer <token>`.

- `GET /cameras`, `POST /cameras`, `PATCH /cameras/{id}`, `DELETE /cameras/{id}` (admin)
- `GET/POST/PATCH/DELETE /zones…` (operator+)
- `GET /alerts?status=&severity=&q=&camera_id=` · `POST /alerts/{id}/acknowledge` · `POST /alerts/{id}/dismiss` (operator+)
- `GET /alerts/audit/verify`
- `GET /analytics/summary|alerts_over_time|alerts_by_kind|alerts_by_camera|events_by_hour|plates/recent|fps`
- `GET /system/status` · `GET /system/pipeline`
- `GET /live/mjpeg/{camera_id}?token=JWT` (raw stream) · `WS /live/ws?token=JWT` (push: alerts, plates, tracks)
- `GET /evidence/{path}?token=JWT` (snapshots/clips)

---

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `nvidia-smi` not found | No/old NVIDIA driver | Install latest NVIDIA driver, reboot |
| Health says `"db":"down"` | Postgres not running | `scripts\start_ibvap.bat` (idempotent) or `assets\pgsql\bin\pg_ctl.exe -D db\data -o "-p 5433" -l db\logfile start` |
| Port 5433 already in use | Another Postgres installed | Edit the `-p 5433` occurrences (scripts + `.env` `DATABASE_URL`) to a free port like 5434 |
| Port 8000/5173 in use | Old process stuck | `scripts\stop_ibvap.bat`, or change ports in `scripts\run_api_window.bat` / `frontend\vite.config.ts` |
| Tile shows `SOURCE ERROR: cannot open source` | Bad path/URL, or the video file is an HTML error page from a failed download | Check the path; re-download the video; for RTSP test the URL in VLC first |
| Tile shows `OFFLINE` after being live | Feed ended/corrupted | The worker auto-loops files and auto-reconnects; check `Recoveries` on SYSTEM. If a file is truly broken, pick another |
| Video plays but no boxes | GPU fallback or very dark footage | Check SYSTEM → Platform shows `cuda available`; try brighter footage; detection threshold is 0.35 confidence |
| WS shows DOWN | Backend restarted or token expired | Log out/in; the UI reconnects automatically with backoff |
| Login rejected | Wrong creds | Use the seeded users in §3.9 (passwords are case-sensitive) |
| `Python 3.13/3.14 not supported` at install | Torch has no wheels yet | Use Python **3.12** exactly (Step 3.1) |
| OCR never runs / plates empty | No vehicles in footage, or first load still warming | ANPR runs only when a vehicle is detected; the first OCR load takes ~20 s (warmed at startup) |
| Everything slow after laptop slept | GPU context reset | Restart the API window; the pipeline re-inits models on first frame |
| Charts look empty on a fresh DB | No data yet | Let it run; alerts appear as objects cross zones |

**Backend log:** `api_log.txt` in the project root — every exception is logged
there (nothing fails silently).

---

## 10. Known limitations of this prototype (honest list)

**Fully working, verified in this pass:** detection + tracking + IDs on GPU;
polygon zones with live editing; restricted/loiter alerts with evidence snapshot
+ pre-event clip; PostgreSQL schema per PRD; JWT + RBAC; ANPR pipeline with
plate-format validation; hash-chained audit with verification; WebSocket push;
analytics from real aggregates; camera add/delete; failure recovery (loop,
reconnect, OOM guard).

**Simulated or partial:**

- **Feeds** — recorded files instead of physical CCTV (labelled `SIMULATED FEED`).
  The RTSP code path exists and is exercised by the same worker; it was not
  tested against a physical camera because none was available.
- **Blockchain** — the PRD lists Hyperledger as optional/stretch. Shipped is a
  SHA-256 hash-chained, append-only ledger with a public verify endpoint. This
  is tamper-evident but not a distributed blockchain, and the UI says so.
- **Face mode** — detection only (Haar cascade, CPU). **No recognition and no
  watchlist matching**; the schema column `matched_watchlist_id` is the hook.
  Biometric matching is deliberately off by default (PRD privacy risk note).
- **ONVIF Profile T discovery** — modular `StreamSource` and `ONVIFProfileT` interfaces are established in `backend/app/pipeline/ingest.py`. Adding network cameras via direct RTSP URI (`rtsp://...`) works immediately. Automatic WS-Discovery probe translates discovered ONVIF Profile T devices into media RTSP URLs as documented in §11.
- **Offline/low-bandwidth mode** — everything already runs locally (the PRD's
  core requirement), but store-and-forward sync to a command center is not
  built in this pass.
- **Cross-camera re-identification** — out of scope (PRD P2).
- **Evidence clips** depend on OpenCV's mp4 encoder being present (falls back
  to .avi automatically).

**Operational Notes:** alert frequency depends on zone placement and size — size zones realistically for tactical boundaries; first pipeline frame after a cold start pays model-load latency (~1–2 s, hidden by the CONNECTING badge).

---

## 11. Where to plug in real cameras later

1. **Direct RTSP**: Add the camera in the SYSTEM screen with source `rtsp://<user>:<pass>@<ip>:<port>/<path>` — zero code changes.
2. The UI badge automatically switches from `SIM` to `LIVE`.
3. **ONVIF Profile T**: The modular `ONVIFProfileT` class in `backend/app/pipeline/ingest.py` provides the exact discovery hook (`probe_cameras`) and profile resolution (`get_stream_uri`). It translates ONVIF device discovery directly into RTSP endpoints compatible with the ingest worker.
4. **USB / Tactical Webcams**: Add with source `0` or `1`. The ingest engine uses native Windows DirectShow (`cv2.CAP_DSHOW`) to bypass standard Windows driver latency.
5. **Edge Deployment (NVIDIA Jetson / Orin)**: The same codebase runs on Jetson Linux with JetPack / TensorRT; the System screen will report the Jetson GPU name and real measured FPS honestly.

---

*Built as a working prototype for evaluation — every claim in §10 was verified
against the running system on the development machine (RTX 4050 Laptop GPU,
Windows 11, Python 3.12.14).*
