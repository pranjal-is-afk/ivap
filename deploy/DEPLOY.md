# Deploying IBVAP — free & fast paths

Two ways to get a shareable URL. Neither needs a paid account or a GPU in the cloud.

| Path | Time to live URL | What judges see | Hardware used |
|---|---|---|---|
| **A. Local + Cloudflare quick tunnel** | ~3 minutes | Full GPU pipeline, real measured FPS (7.9 FPS / 20–130 ms) | Your RTX 4050 (laptop must stay on) |
| **B. HF Spaces (Docker) + Neon Postgres** | ~45–60 min build | Same UI, CPU pipeline (~2–5 FPS) | Free cloud (2 vCPU, 16 GB RAM) |

Both paths serve the built frontend from the API's own origin (FastAPI now serves
`frontend/dist` automatically), so auth, MJPEG and WebSockets need no CORS setup.

---

## Path A — demo in 3 minutes (tunnel to your machine)

Best for: live demo day. Full GPU speed, your exact verified build, zero cloud setup.
The URL is temporary and only valid while the laptop runs.

1. Start the stack normally: `scripts\start_ibvap.bat` (Postgres + API + UI).
2. Download the tunnel client once:
   `powershell -ExecutionPolicy Bypass -File deploy\fetch_cloudflared.ps1`
3. Open the tunnel:
   `cloudflared tunnel --url http://127.0.0.1:8000`
   → prints something like `https://ibvap-demo.RandomWords.trycloudflare.com`
4. Share that URL. Log in with the seeded credentials (USER_MANUAL §3).

**Change the JWT_SECRET first if the URL goes to anyone outside the team** — it is
the signing key for every account (see `deploy/env.cloud.example`). With a tunnel
you set it by editing `.env` (`JWT_SECRET=...`) and restarting the API.

Notes:
- Everything is served from the one origin — no CORS edits needed.
- Cloudflare's quick tunnel has no bandwidth limit for this use case; MJPEG (~4 Mbps
  per open feed) is fine.
- Closing `cloudflared` (Ctrl+C) kills the URL. Nothing else to clean up.

---

## Path B — free permanent URL (HF Spaces + Neon Postgres)

Best for: a link that works when your laptop is off. The pipeline runs on CPU in a
free Docker Space (2 vCPU / 16 GB — the only free host with enough RAM for
torch + OCR; typical free tiers elsewhere offer 512 MB and will OOM).

Expect ~2–5 FPS per feed on CPU and an honest SIMULATED FEED experience — same
pipeline, same DB, same alerts. The System page will truthfully report "cpu".

### 1. Database (5 min)

1. Create a free account at neon.tech → **New project** → Postgres 16.
2. Copy the **pooled** connection string (…`-pooler`…, `?sslmode=require`).
   That is your `DATABASE_URL`. The free tier is more than enough: the schema is
   small; streams hold in-memory; evidence files are written in-container.

### 2. Image (Docker)

A `Dockerfile` ships at repo root. Build context is the repo root; it builds the
frontend, installs CPU-torch (pinned 2.3.1) + requirements, bakes the demo videos
and `yolo11n.pt` in, and starts via `deploy/entrypoint.py` (maps `$PORT` → uvicorn).

To run it yourself on any Docker host:

```bash
docker build -t ibvap .
docker run --rm -p 8000:8000 \
  -e DATABASE_URL="postgresql://...neon.tech/neondb?sslmode=require" \
  -e JWT_SECRET="long-random-string" \
  -e IBVAP_DEMO=1 \
  ibvap
```

### 3. Host it free on HF Spaces (~45–60 min, mostly the build queue)

1. huggingface.co → **New Space** → SDK: **Docker** → hardware: free CPU basic.
2. Add these in **Settings → Variables & secrets**:
   | Name | Value |
   |---|---|
   | `DATABASE_URL` | your Neon pooled string (`sslmode=require`) |
   | `JWT_SECRET` | long random string |
   | `IBVAP_DEMO` | `1` |
3. Push the repo (Dockerfile at root) to the Space's git repo:
   ```bash
   git clone https://huggingface.co/spaces/<you>/ibvap
   cd ibvap
   # copy the project files in, then:
   git add . && git commit -m "IBVAP deploy" && git push
   ```
   The Space builds (~30–45 min; torch + ultralytics are chunky) and then boots.
4. The app is live at `https://<you>-ibvap.hf.space`.

First boot after build: schema + seed run automatically against Neon; both demo
cameras auto-start (IBVAP_DEMO=1). Expect the Space to sleep after 48 h idle —
a visit restarts it (state is in Neon, so nothing is lost).

---

## What's different in a cloud deployment (honest deltas)

- **CPU inference** — the System page will show `cpu` and FPS will be lower. This is
  the same code path; torch simply runs without CUDA. Nothing is faked.
- **Ephemeral evidence** — snapshots/clips live in the container, not Neon. A Space
  restart wipes `evidence/`. (If you need durable evidence on the free tier, mount a
  HF persistent storage add-on or write to object storage — a deliberate v2 item.)
- **The `<user>@<host>` account problem doesn't exist here** — seeded users are the
  login (admin/operator/viewer; see USER_MANUAL). Rotate passwords before sharing.
- **One container, one worker.** Camera threads live in the web process. Fine for a
  demo; a production split (ingest worker ↔ API) is documented in USER_MANUAL §12.

## Hardening checklist before sharing a URL

1. `JWT_SECRET` set to a long random value (env var, not the default).
2. Seeded account passwords rotated (PATCH `/api/auth/users/{id}` as admin, or
   update `DEFAULT_USERS` + reseed).
3. Demo cameras only — do not expose credentials-bearing RTSP URLs of real cameras
   through a public tunnel.
4. Enable TLS at the edge (both paths above terminate TLS for you).
