# Load .env into os.environ BEFORE any settings module reads env vars.
# Without this, base.py runs first with empty env, locking in defaults
# even though production.py later calls load_dotenv() — too late.
try:
    import os
    from pathlib import Path
    from dotenv import load_dotenv
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    _ENV_PATH = _PROJECT_ROOT / ".env"
    if _ENV_PATH.exists():
        load_dotenv(_ENV_PATH)
except ImportError:
    pass

from .base import *

# Try to load local settings first
try:
    from .local import *
    print("Loaded local settings.")
except ImportError:
    from .production import *
    print("Loaded production settings.")