"""AJAP emergency startup guard.

Temporary diagnostic entry point: load the real run_bot stack, but if Discord
login fails, print exactly one concise error and keep the Railway process alive.
This prevents restart/log storms from hiding the actual exception. No database
reset or destructive action is performed here.
"""

import os
import time

PRIMARY_RAILWAY_PROJECT_ID = "6abcd5b2-6995-4e18-b7f1-be32f6298fdc"
CURRENT_RAILWAY_PROJECT_ID = (os.getenv("RAILWAY_PROJECT_ID") or "").strip()

if CURRENT_RAILWAY_PROJECT_ID and CURRENT_RAILWAY_PROJECT_ID != PRIMARY_RAILWAY_PROJECT_ID:
    print(
        "AJAP secondary Railway: Discord gateway disabled | "
        f"current_project={CURRENT_RAILWAY_PROJECT_ID} | primary={PRIMARY_RAILWAY_PROJECT_ID}",
        flush=True,
    )
    while True:
        time.sleep(3600)

print(
    "AJAP production startup guard: loading real bot stack | "
    f"project={CURRENT_RAILWAY_PROJECT_ID or 'local'}",
    flush=True,
)

try:
    import run_bot  # noqa: F401,E402
except BaseException as exc:
    status = getattr(exc, "status", None)
    code = getattr(exc, "code", None)
    detail = str(exc).replace("\n", " ")[:1200]
    print(
        "AJAP DISCORD/STARTUP FATAL | "
        f"type={type(exc).__name__} | status={status} | code={code} | detail={detail}",
        flush=True,
    )
    # Keep the deployment alive so Railway does not restart-loop and flood logs.
    while True:
        time.sleep(3600)
