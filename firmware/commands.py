"""Inbound command dispatch with idempotency.

Commands are at-least-once (broker retries + platform relay sweep), so every
``command_id`` is remembered and its effect applied exactly once. A handler
returns ``(ack_detail, effect)``; the orchestrator applies the effect (reboot,
interval change, status probe) after the ack is published.

Pure logic — host-testable. Hardware actions are represented as effect dicts.
"""

import json
import time

_CMD_TYPES = frozenset(("ping", "status_probe", "set_interval", "reboot"))
_MIN_INTERVAL_S = 5
_MAX_INTERVAL_S = 3600
_DUP_TTL_S = 24 * 3600


class CommandRejected(ValueError):
    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class CommandRegistry:
    def __init__(self, max_recent: int = 256, now=None):
        self.max_recent = max_recent
        self._recent: dict[str, int] = {}
        if now is not None:
            self._now = now
        else:
            self._now = getattr(time, "time", lambda: 0)

    def _timestamp(self):
        return self._now()

    def handle(self, command: dict):
        """Return ``(ack_frame, effect)`` or ``(None, None)`` if not ackable."""
        command_id = command.get("command_id")
        cmd_type = command.get("type")
        payload = command.get("payload") or {}
        if not command_id or not cmd_type:
            return None, None
        if not isinstance(payload, dict):
            payload = {}

        now = self._timestamp()
        self._prune(now)
        fresh = command_id not in self._recent
        if fresh:
            self._recent[command_id] = now

        if cmd_type not in _CMD_TYPES:
            self._remember(command_id, now)
            return self._ack(command_id, "rejected", "unsupported_command:%s" % cmd_type), None

        if not fresh:
            return self._ack(command_id, "executed", "duplicate"), None

        try:
            detail, effect = self._dispatch(cmd_type, payload)
        except CommandRejected as exc:
            return self._ack(command_id, "rejected", exc.detail), None
        return self._ack(command_id, "executed", detail), effect

    def _dispatch(self, cmd_type: str, payload: dict):
        if cmd_type == "ping":
            return "ping ok", None
        if cmd_type == "status_probe":
            return "probe requested", {"action": "status_probe"}
        if cmd_type == "set_interval":
            seconds = payload.get("seconds")
            try:
                seconds = int(seconds)
            except (TypeError, ValueError):
                raise CommandRejected("invalid interval")
            seconds = max(_MIN_INTERVAL_S, min(seconds, _MAX_INTERVAL_S))
            return "sampling interval now %d s" % seconds, {"action": "set_interval", "seconds": seconds}
        if cmd_type == "reboot":
            return "rebooting", {"action": "reboot"}
        raise CommandRejected("unsupported_command:%s" % cmd_type)

    def _ack(self, command_id: str, status: str, detail: str):
        return {"command_id": command_id, "status": status, "detail": detail}

    def _remember(self, command_id: str, now: int) -> None:
        if len(self._recent) >= self.max_recent:
            oldest = min(self._recent, key=self._recent.get)
            del self._recent[oldest]
        self._recent[command_id] = now

    def _prune(self, now: int) -> None:
        cutoff = now - _DUP_TTL_S
        for command_id in [cid for cid, ts in self._recent.items() if ts < cutoff]:
            del self._recent[command_id]

    @staticmethod
    def dump(command: dict) -> str:
        return json.dumps(command, separators=(",", ":"))