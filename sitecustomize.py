"""Railway runtime defaults for persistent SQLite storage.

Python imports this module automatically at startup (when it is available on
sys.path). If a Railway Volume is attached, point the bot's existing DB_PATH
at that persistent mount without changing the rest of bot.py.
"""

import os
from pathlib import Path


volume_path = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")

if volume_path and not os.getenv("DB_PATH"):
    persistent_db = Path(volume_path) / "ajap_market.db"
    os.environ["DB_PATH"] = str(persistent_db)
