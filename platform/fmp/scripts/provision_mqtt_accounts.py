"""Provision MQTT accounts and per-device ACL rules (G-001).

The broker is deny-by-default: it authenticates against EMQX's built-in
database and denies anything without an ACL rule. This script turns that policy
into working identities, idempotently, via the EMQX 5 REST API.

It provisions:

* one account per registered :class:`~fmp.models.IoTGateway`, username = the
  gateway MAC, restricted to ``fuel/<mac>/#`` — a compromised device can publish
  only its own frames and cannot read or spoof another device's;
* one platform service account for the ingestion engine, which needs the
  ingestion topics, all gateway topics and the command channels.

Device passwords are derived deterministically from
``MQTT_DEVICE_PASSWORD_SEED`` + the MAC so the same fleet gets the same
credentials on re-provisioning (and can be printed once and shipped to the
devices). Setting an explicit seed is mandatory in production: without it the
script refuses to run rather than minting guessable credentials.

Usage::

    EMQX_API_KEY=fuel-platform-bootstrap EMQX_API_SECRET="$(cat infra/emqx/secrets/api_keys.txt | cut -d: -f2)" \
    MQTT_DEVICE_PASSWORD_SEED="$(openssl rand -hex 32)" \
    python -m fmp.scripts.provision_mqtt_accounts

    # report only
    python -m fmp.scripts.provision_mqtt_accounts --dry-run
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import logging
import sys
import urllib.error
import urllib.request

from sqlalchemy import select

from fmp.core.config import get_settings
from fmp.core.database import async_session_factory
from fmp.models import IoTGateway

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("provision_mqtt")

def emqx_acl_pattern(mac: str) -> str:
    """Topic filter a single gateway is allowed to use (EMQX ``#`` wildcard)."""
    return f"fuel/{mac}/#"


#: Topics the platform's own ingestion service needs (EMQX ``#`` wildcard).
SERVICE_TOPICS = [
    "ingestion/#",
    "fuel/#",
    "iot/#",
]


def device_rules(mac: str) -> list[dict]:
    """A gateway may publish and subscribe only on its own topic space."""
    return [
        {"action": "publish", "topic": emqx_acl_pattern(mac), "permission": "allow"},
        {"action": "subscribe", "topic": emqx_acl_pattern(mac), "permission": "allow"},
        {"action": "subscribe", "topic": f"iot/commands/{mac}/#", "permission": "allow"},
    ]


def service_rules() -> list[dict]:
    """The ingestion engine is the only identity that may use shared topics."""
    return [
        {"action": "publish", "topic": topic, "permission": "allow"} for topic in SERVICE_TOPICS
    ] + [
        {"action": "subscribe", "topic": topic, "permission": "allow"}
        for topic in ("fuel/#", "iot/commands/#")
    ]


def derive_device_password(seed: str, mac: str) -> str:
    """Deterministic per-device password from a fleet seed and the device MAC."""
    digest = hmac.new(seed.encode("utf-8"), mac.encode("utf-8"), hashlib.sha256).digest()
    return "fmd_" + base64.urlsafe_b64encode(digest).decode().rstrip("=")


class EmqxApi:
    """Minimal EMQX 5 REST client (HTTP basic auth with an API key, JSON in/out).

    EMQX 5's REST API rejects dashboard credentials ("BAD_API_KEY_OR_SECRET"); it
    requires an API key/secret, which is why the broker bootstrap file exists.
    """

    def __init__(self, base_url: str, username: str, password: str, timeout: int = 15):
        self.base_url = base_url.rstrip("/")
        self._auth = base64.b64encode(f"{username}:{password}".encode()).decode()
        self._timeout = timeout

    def _request(self, method: str, path: str, payload: dict | None = None):
        data = None
        headers = {"Authorization": f"Basic {self._auth}", "Accept": "application/json"}
        if payload is not None:
            # urllib requires bytes; a dict body raises "can't concat str to bytes".
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            f"{self.base_url}/api/v5{path}", data=data, headers=headers, method=method
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            body = resp.read()
            return resp.status, (json.loads(body) if body else None)

    _USERS_PATH = "/authentication/password_based:built_in_database/users"

    def list_users(self) -> dict:
        # EMQX 5.8 returns ``user_id`` for this endpoint.
        _status, data = self._request("GET", self._USERS_PATH)
        return {u.get("user_id") or u.get("username"): u for u in (data or {}).get("data", [])}

    def upsert_user(self, username: str, password: str) -> str:
        """Create the user if absent; rotate the password if present."""
        if username in self.list_users():
            status, _ = self._request(
                "PUT",
                f"{self._USERS_PATH}/{username}",
                {"password": password, "is_superuser": False},
            )
            return "rotated" if status in (200, 204) else "unknown"
        self._request(
            "POST",
            self._USERS_PATH,
            {"user_id": username, "password": password, "is_superuser": False},
        )
        return "created"

    # EMQX 5.8 keeps per-user ACL rules under .../rules/users.
    _RULES_BASE = "/authorization/sources/built_in_database/rules/users"

    def list_rules(self) -> dict:
        _status, data = self._request("GET", self._RULES_BASE)
        return {r["subject"]: r for r in (data or {}).get("data", [])}

    def delete_rule(self, subject: str) -> None:
        try:
            self._request("DELETE", f"{self._RULES_BASE}/{subject}")
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise

    def create_rule(self, subject: str, rules: list[dict]) -> None:
        """Install (replace) the ACL rules for one user.

        EMQX 5.8 takes a LIST of ``{username, rules:[{action,topic,permission}]}``.
        """
        self._request("POST", self._RULES_BASE, [{"username": subject, "rules": rules}])


async def _gateway_macs() -> list[str]:
    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(IoTGateway.gateway_mac).where(IoTGateway.is_active.is_(True))
            )
        ).scalars().all()
    return sorted({m for m in rows if m})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print the plan, change nothing")
    parser.add_argument(
        "--strict-seed",
        action="store_true",
        help="refuse to run without MQTT_DEVICE_PASSWORD_SEED",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    if not settings.EMQX_API_KEY or not settings.EMQX_API_SECRET:
        logger.error(
            "EMQX_API_KEY / EMQX_API_SECRET are required to provision broker accounts. "
            "Create infra/emqx/secrets/api_keys.txt from infra/emqx/secrets/api_keys.txt.example "
            "(it is git-ignored because it holds a live administrative credential) "
            "and put the same pair in .env."
        )
        return 2
    if settings.EMQX_API_SECRET.startswith("REPLACE_ME"):
        logger.error(
            "EMQX_API_SECRET is still the placeholder from the example file. "
            "Generate a real secret with: openssl rand -hex 32"
        )
        return 2
    if not settings.MQTT_DEVICE_PASSWORD_SEED and (args.strict_seed or settings.ENVIRONMENT == "prod"):
        logger.error(
            "MQTT_DEVICE_PASSWORD_SEED must be set (generate with: openssl rand -hex 32). "
            "Refusing to derive device credentials from an empty seed."
        )
        return 2
    if not settings.MQTT_SERVICE_USERNAME or not settings.MQTT_SERVICE_PASSWORD:
        logger.error("MQTT_SERVICE_USERNAME / MQTT_SERVICE_PASSWORD must be set for the ingestion service")
        return 2

    import asyncio

    macs = asyncio.run(_gateway_macs())
    logger.info("provisioning %d gateway account(s) + 1 service account", len(macs))

    if args.dry_run:
        for mac in macs:
            logger.info("would create user %s with topics %s", mac, emqx_acl_pattern(mac))
        logger.info("would create service user %s with topics %s", settings.MQTT_SERVICE_USERNAME, SERVICE_TOPICS)
        return 0

    api = EmqxApi(settings.EMQX_API_URL, settings.EMQX_API_KEY, settings.EMQX_API_SECRET)
    try:
        api.list_users()  # fail fast with a clear message if the broker is unreachable
    except urllib.error.URLError as exc:
        logger.error("cannot reach the EMQX API at %s: %s", settings.EMQX_API_URL, exc)
        return 1

    created = rotated = 0
    try:
        for mac in macs:
            password = derive_device_password(settings.MQTT_DEVICE_PASSWORD_SEED, mac)
            outcome = api.upsert_user(mac, password)
            created += outcome == "created"
            rotated += outcome == "rotated"
            try:
                api.delete_rule(mac)
            except urllib.error.HTTPError:
                pass
            api.create_rule(mac, device_rules(mac))
            logger.info("account %s: %s", mac, outcome)
        api.upsert_user(settings.MQTT_SERVICE_USERNAME, settings.MQTT_SERVICE_PASSWORD)
        try:
            api.delete_rule(settings.MQTT_SERVICE_USERNAME)
        except urllib.error.HTTPError:
            pass
        api.create_rule(settings.MQTT_SERVICE_USERNAME, service_rules())
    except urllib.error.HTTPError as exc:
        logger.error("broker rejected provisioning: %s %s", exc.code, exc.read().decode()[:300])
        return 1
    logger.info(
        "done: %d created, %d rotated, %d ACL rules in place",
        created, rotated, len(macs) + 1,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
