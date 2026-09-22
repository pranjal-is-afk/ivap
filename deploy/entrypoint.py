#!/usr/bin/env python3
"""Container entrypoint: map $PORT -> uvicorn (HF Spaces sets PORT).

Env contract (see deploy/DEPLOY.md):
  DATABASE_URL   required, Postgres (Neon pooled string works)
  JWT_SECRET     required in any exposed deployment
  IBVAP_DEMO     1 -> auto-start seeded demo cameras
  PORT           provided by the platform (default 8000)
"""
import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        workers=1,
        log_level="info",
    )
