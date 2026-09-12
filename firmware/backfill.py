"""Optional HTTPS batch backfill of buffered frames.

Used only when configured (``BACKFILL_URL``) and MQTT is unreachable for a long
stretch. Requires the ``urequests`` package (MicroPython). Non-fatal failures.
"""

import json


def post_frames(frames: list[dict], url: str, *, timeout_s: float = 10.0) -> bool:
    if not frames or not url:
        return False
    try:
        import urequests

        response = urequests.post(
            url + "/api/v1/ingest/backfill",
            data=json.dumps(frames, separators=(",", ":")),
            headers={"Content-Type": "application/json"},
            timeout=timeout_s,
        )
        ok = response.status_code in (200, 201)
        response.close()
        return ok
    except (ImportError, OSError, ValueError):
        return False