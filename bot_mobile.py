"""Optional AJPA startup that serves Discord + the read-only mobile API.

Production can keep using ``python bot.py`` unchanged. For a mobile-enabled
preview/deployment use ``python bot_mobile.py`` and the API will bind to the
Railway PORT while the existing Discord bot keeps its normal startup path.
"""

import os

# sitecustomize is loaded automatically by Python, but importing it explicitly
# documents that DB_PATH must be resolved before the read-only server starts.
import sitecustomize  # noqa: F401

os.environ.setdefault("AJPA_MOBILE_API_ENABLED", "1")

from mobile_read_api import start_mobile_read_api  # noqa: E402

start_mobile_read_api()

# Keep every existing bot guard/patch/startup exactly as production uses it.
import bot  # noqa: F401,E402
