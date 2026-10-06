"""Secret masking for notification-channel configuration.

Channel credentials (SMPP password, WhatsApp token, SMTP password, webhook
signing secrets) live in ``notification_gateways.config_json``. They must be
**write-only** over the API:

* ``mask_config`` renders a config safe for any reader — key names are kept so
  the UI can show which fields are configured, values are replaced with
  :data:`MASK`.
* ``merge_config`` applies a partial update: a masked or absent secret keeps the
  stored value, so an operator editing "priority" can never silently wipe the
  password, and can never read it back either.
"""
from __future__ import annotations

MASK = "********"

#: Substrings that mark a key as secret regardless of channel. Matched
#: case-insensitively against the lowercased key.
SECRET_KEY_MARKERS: tuple[str, ...] = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "credential",
    "authorization",
    "auth",
    "system_id",
    "client_secret",
)

#: Keys that are secret for a specific channel but are shared/identifier-like
#: enough that the generic marker list must be extended per channel.
CHANNEL_SECRET_KEYS: dict[str, tuple[str, ...]] = {
    "smpp": ("system_id", "password"),
    "sms": ("system_id", "password"),
    "whatsapp": ("access_token", "phone_number_id", "app_secret"),
    "email": ("password", "username"),
    "webhook": ("secret", "signing_secret", "token"),
}


def is_secret_key(key: str, channel_type: str | None = None) -> bool:
    lowered = key.lower()
    if channel_type and lowered in CHANNEL_SECRET_KEYS.get(channel_type, ()):
        return True
    return any(marker in lowered for marker in SECRET_KEY_MARKERS)


def mask_config(config: dict | None, channel_type: str | None = None) -> dict:
    """Return a copy of ``config`` with every secret value replaced by ``MASK``."""
    if not config:
        return {}
    return {
        key: (MASK if is_secret_key(key, channel_type) else value)
        for key, value in config.items()
    }


def is_masked(value) -> bool:
    """True when a client sent back our own mask (or an empty value)."""
    return value is None or (isinstance(value, str) and value.strip() in ("", MASK))


def merge_config(
    stored: dict | None,
    incoming: dict | None,
    channel_type: str | None = None,
) -> dict:
    """Merge a client-supplied config over the stored one.

    Secrets are preserved when the client omits them or echoes :data:`MASK`
    back. Sending a new secret value replaces the stored one. Non-secret keys
    are replaced verbatim, and keys the client drops entirely are removed
    (an explicit ``{}`` clears non-secret settings).
    """
    stored = dict(stored or {})
    if incoming is None:
        return stored
    merged = dict(stored)
    for key, value in incoming.items():
        if is_secret_key(key, channel_type):
            if is_masked(value):
                # Keep whatever is already stored (mask echo / omitted).
                merged.setdefault(key, MASK if key not in stored else stored[key])
                if key not in stored:
                    merged[key] = MASK
                continue
            merged[key] = value
        else:
            merged[key] = value
    # Drop keys the caller removed, except secrets (never dropped implicitly).
    for key in set(stored) - set(incoming):
        if not is_secret_key(key, channel_type):
            merged.pop(key, None)
    return merged
