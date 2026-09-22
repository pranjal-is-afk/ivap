import sys
from pathlib import Path

# Make `app` importable when running pytest from repo root or backend/
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
