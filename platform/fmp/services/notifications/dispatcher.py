"""Gateway Manager for notification dispatch.

Supports two outbound channels per the dispensing specification:

* **SMPP** (Short Message Peer-to-Peer) for classic SMS to third-party
  carriers that present an SMPP host:port.
* **WhatsApp Business API** (Cloud API) with phone-number-id + access token.

Responsibilities
----------------
* Reliable per-gateway send with configurable retries + exponential backoff.
* Native async SMPP using a raw TCP socket to the SMPP PDU sequence
  (bind → submit_sm → deliver_sm_resp) — no external C library required.
* Persist a :class:`NotificationLog` row per attempt.
"""
from __future__ import annotations

import asyncio
import json
import logging
import struct
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fmp.core.config import get_settings
from fmp.core.database import celery_session_factory
from fmp.models.notifications import NotificationGateway, NotificationLog
from fmp.schemas.notifications import DispatchResult, PendingDispatch

logger = logging.getLogger(__name__)
settings = get_settings()

# SMPP command ids
SMPP_SUBMIT_SM = 0x00000004
SMPP_BIND_TRANSMITTER = 0x00000002
SMPP_BIND_TRANSMITTER_RESP = 0x80000002
SMPP_SUBMIT_SM_RESP = 0x80000004


@dataclass
class SendError(Exception):
    gateway: str
    reason: str


class SMPPClient:
    """Minimal async SMPP transmitter (bind + submit_sm + unbind)."""

    def __init__(self, **cfg: str) -> None:
        self.host = cfg["host"]
        self.port = int(cfg.get("port", 7775))
        self.system_id = cfg["system_id"]
        self.password = cfg["password"]
        self.sender_id = cfg.get("sender_id", "")
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    async def connect(self) -> None:
        self._reader, self._writer = await asyncio.open_connection(
            self.host, self.port
        )
        pdu = _build_bind(self)
        await self._send(pdu)
        resp = await self._recv()
        command_id = struct.unpack("!I", resp[4:8])[0]
        status = struct.unpack("!I", resp[8:12])[0]
        if command_id != SMPP_BIND_TRANSMITTER_RESP or status != 0:
            raise SendError("smpp", f"bind failed status={status}")

    async def send_sms(self, phone: str, text: str) -> str:
        if self._writer is None:
            await self.connect()
        pdu = _build_submit_sm(self, phone, text)
        await self._send(pdu)
        resp = await self._recv()
        command_id = struct.unpack("!I", resp[4:8])[0]
        status = struct.unpack("!I", resp[8:12])[0]
        if command_id != SMPP_SUBMIT_SM_RESP or status != 0:
            raise SendError("smpp", f"submit_sm rejected status={status}")
        # message_id is the tail of the PDU (bytes after status)
        return resp[12:].decode(errors="ignore") or uuid.uuid4().hex

    async def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass
            self._writer = None

    async def _send(self, pdu: bytes) -> None:
        assert self._writer is not None
        self._writer.write(struct.pack("!I", len(pdu)) + pdu)
        await self._writer.drain()

    async def _recv(self) -> bytes:
        assert self._reader is not None
        length = struct.unpack("!I", await self._reader.readexactly(4))[0]
        return await self._reader.readexactly(length)


def _build_bind(client: SMPPClient) -> bytes:
    body = (
        client.system_id.encode() + b"\x00"
        + client.password.encode() + b"\x00"
        + b"CMT\x00"        # system_type
        + struct.pack("!B", 0x34)      # interface_version (SMPP 3.4)
        + struct.pack("!B", 0x05)      # addr_ton
        + struct.pack("!B", 0x01)      # addr_npi
        + client.sender_id.encode() + b"\x00"
    )
    return _pdu(SMPP_BIND_TRANSMITTER, body)


def _build_submit_sm(client: SMPPClient, phone: str, text: str) -> bytes:
    # data_coding 0 = GSM 7-bit (default alphabet); CAPACITY capped at 160.
    payload = text.encode(errors="ignore")[:254]
    body = (
        b"\x00"                        # service_type
        + struct.pack("!B", 0x01)      # source_addr_ton (international)
        + struct.pack("!B", 0x01)      # source_addr_npi
        + client.sender_id.encode() + b"\x00"
        + struct.pack("!B", 0x01)      # dest_addr_ton
        + struct.pack("!B", 0x01)      # dest_addr_npi
        + phone.encode() + b"\x00"
        + struct.pack("!B", 0x00)      # esm_class
        + struct.pack("!B", 0x00)      # protocol_id
        + struct.pack("!B", 0x01)      # priority_flag
        + struct.pack("!B", 0x00)      # schedule_delivery_time (empty)
        + struct.pack("!B", 0x00)      # validity_period (empty)
        + struct.pack("!B", 0x00)      # sm_default_msg_id
        + struct.pack("!B", 0x00)      # data_coding (GSM 7-bit)
        + struct.pack("!B", len(payload))
        + payload
    )
    return _pdu(SMPP_SUBMIT_SM, body)


def _pdu(command_id: int, body: bytes) -> bytes:
    header = struct.pack("!IIII", len(body) + 16, command_id, 0, 0)
    return header + body


class WhatsAppClient:
    """WhatsApp Business Cloud API messenger (https://graph.facebook.com)."""

    def __init__(self, **cfg: str) -> None:
        self.token = cfg["access_token"]
        self.phone_number_id = cfg["phone_number_id"]
        self.api_version = cfg.get("api_version", "v21.0")
        self.base = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"

    async def send_text(self, phone: str, text: str) -> str:
        import urllib.request

        body = json.dumps(
            {
                "messaging_product": "whatsapp",
                "to": phone.lstrip("+"),
                "type": "text",
                "text": {"preview_url": False, "body": text},
            }
        ).encode()
        req = urllib.request.Request(
            self.base,
            data=body,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        # run blocking call off the event loop
        resp = await asyncio.to_thread(urllib.request.urlopen, req)
        payload = json.loads(resp.read().decode())
        if payload.get("messages"):
            return payload["messages"][0]["id"]
        raise SendError("whatsapp", f"no message id in response: {payload}")


# --------------------------------------------------------------------------
# Orchestrator
# --------------------------------------------------------------------------
class NotificationDispatcher:
    """Sends one :class:`PendingDispatch`, using ``session`` for logging."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _message_for(self, item: PendingDispatch) -> str:
        return (
            f"Fuel allowance authorized. Employee {item.employee_name} ({item.employee_id}): "
            f"{item.liters:.2f} L. Authorization code: {item.code}. "
            + (f"Invoice {item.invoice_number}. " if item.invoice_number else "")
            + "Valid 7 days. Do not share."
        )

    async def dispatch(self, item: PendingDispatch) -> DispatchResult:
        """Deliver a code to one employee with cross-gateway failover + retries."""
        session = self._session
        gateways = await self._load_active_gateways(session, item.company_id)
        if not gateways:
            return DispatchResult(
                allocation_id=item.allocation_id,
                phone=item.phone,
                channel=item.channel or settings.DEFAULT_NOTIFICATION_CHANNEL,
                status="FAILED",
                error="no active notification gateway configured",
            )

        text = self._message_for(item)
        last_error: str | None = None

        for attempt in range(1, settings.NOTIFY_MAX_RETRIES + 1):
            for gw in gateways:
                channel = item.channel or settings.DEFAULT_NOTIFICATION_CHANNEL
                if gw.type not in CHANNEL_GATEWAY_TYPES.get(channel, {channel}):
                    continue
                try:
                    provider_id = await self._send_via(gw, item.phone, text)
                except Exception as exc:  # noqa: BLE001
                    last_error = f"{exc}"
                    await self._log(
                        session, item, gw.id, channel, status="FAILED",
                        error=f"{exc}", retry=attempt,
                    )
                    logger.warning("gateway %s failed (attempt %d): %s", gw.name, attempt, exc)
                    continue

                await self._log(
                    session, item, gw.id, channel, status="SENT",
                    provider_msg_id=provider_id, retry=attempt,
                )
                return DispatchResult(
                    allocation_id=item.allocation_id,
                    phone=item.phone,
                    channel=channel,
                    status="SENT",
                    gateway_id=gw.id,
                    provider_message_id=provider_id,
                )

            if attempt < settings.NOTIFY_MAX_RETRIES:
                await asyncio.sleep(settings.NOTIFY_RETRY_BACKOFF * attempt)

        return DispatchResult(
            allocation_id=item.allocation_id,
            phone=item.phone,
            channel=item.channel or settings.DEFAULT_NOTIFICATION_CHANNEL,
            status="FAILED",
            error=last_error,
        )

    async def _send_via(
        self, gw: NotificationGateway, recipient: str, text: str
    ) -> str:
        return await send_via_gateway(gw, recipient, text)

    async def _load_active_gateways(
        self, session: AsyncSession, company_id: uuid.UUID | None = None
    ) -> list[NotificationGateway]:
        """Active channels visible to a tenant: its own plus platform-wide ones."""
        stmt = (
            select(NotificationGateway)
            .where(NotificationGateway.is_active.is_(True))
            .order_by(NotificationGateway.priority.asc())
        )
        if company_id is not None:
            from sqlalchemy import or_

            stmt = stmt.where(
                or_(
                    NotificationGateway.company_id == company_id,
                    NotificationGateway.company_id.is_(None),
                )
            )
        res = await session.execute(stmt)
        return list(res.scalars().all())

    async def _log(
        self,
        session: AsyncSession,
        item: PendingDispatch,
        gateway_id: uuid.UUID | None,
        channel: str,
        status: str,
        provider_msg_id: str | None = None,
        error: str | None = None,
        retry: int = 0,
    ) -> None:
        await log_delivery(
            session,
            gateway_id=gateway_id,
            channel=channel,
            recipient=item.phone,
            status=status,
            provider_message_id=provider_msg_id,
            error=error,
            retry=retry,
            event_type="dispense_code",
            event_ref=str(item.allocation_id),
            allocation_id=item.allocation_id,
            company_id=item.company_id,
        )


# ---------------------------------------------------------------------------
# Channel senders (single source of truth — also used by rule dispatch)
# ---------------------------------------------------------------------------

#: "sms" is the operator-facing channel name; it is carried by SMPP gateways.
CHANNEL_GATEWAY_TYPES: dict[str, set[str]] = {
    "sms": {"sms", "smpp"},
    "smpp": {"sms", "smpp"},
    "whatsapp": {"whatsapp"},
    "email": {"email"},
    "webhook": {"webhook"},
}


async def send_via_gateway(gw: NotificationGateway, recipient: str, text: str) -> str:
    """Send one message through a concrete gateway; returns provider message id."""
    cfg = json.loads(gw.config_json) if gw.config_json else {}
    if gw.type in ("sms", "smpp"):
        client = SMPPClient(**cfg)
        try:
            return await client.send_sms(recipient, text)
        finally:
            await client.close()
    if gw.type == "whatsapp":
        client = WhatsAppClient(**cfg)
        return await client.send_text(recipient, text)
    if gw.type == "email":
        return await _send_smtp(cfg, recipient, text)
    if gw.type == "webhook":
        return await _post_webhook(cfg, recipient, text)
    raise SendError(gw.type, "unknown gateway type")


async def _send_smtp(cfg: dict, to: str, text: str) -> str:
    """RFC-compliant plain-text email over SMTP/SMTPS (stdlib only)."""
    import smtplib
    from email.message import EmailMessage

    host = cfg["host"]
    port = int(cfg.get("port", 587))
    username = cfg.get("username")
    password = cfg.get("password")
    use_tls = bool(cfg.get("tls", True))
    sender = cfg.get("from") or username or "alerts@fuel-platform.local"
    subject = cfg.get("subject") or "Fuel platform alert"

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text, charset="utf-8")

    def _send() -> None:
        cls = smtplib.SMTP_SSL if use_tls and port == 465 else smtplib.SMTP
        with cls(host, port, timeout=20) as smtp:
            if use_tls and port != 465:
                smtp.starttls()
            if username:
                smtp.login(username, password or "")
            smtp.send_message(msg)

    await asyncio.to_thread(_send)
    return f"smtp:{host}:{port}"


async def _post_webhook(cfg: dict, ref: str, text: str) -> str:
    """POST a JSON event document to the configured URL."""
    import urllib.request

    url = cfg["url"]
    body = json.dumps({"event": cfg.get("event", "alert"), "ref": ref, "text": text}).encode()
    headers = {"Content-Type": "application/json"}
    if cfg.get("auth_header"):
        headers["Authorization"] = cfg["auth_header"]
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    resp = await asyncio.to_thread(urllib.request.urlopen, req)
    if resp.status >= 400:
        raise SendError("webhook", f"webhook returned {resp.status}")
    return f"webhook:{resp.status}"


async def log_delivery(
    session: AsyncSession,
    *,
    gateway_id: uuid.UUID | None,
    channel: str,
    recipient: str,
    status: str,
    provider_message_id: str | None = None,
    error: str | None = None,
    retry: int = 0,
    event_type: str = "dispense_code",
    event_ref: str | None = None,
    allocation_id: uuid.UUID | None = None,
    company_id: uuid.UUID | None = None,
) -> None:
    session.add(
        NotificationLog(
            allocation_id=allocation_id,
            company_id=company_id,
            event_type=event_type,
            event_ref=event_ref,
            gateway_id=gateway_id,
            channel=channel,
            recipient=recipient,
            status=status,
            provider_message_id=provider_message_id,
            error_message=(error or None),
            retry_count=retry,
            sent_at=datetime.now(timezone.utc) if status == "SENT" else None,
        )
    )
    await session.commit()


async def _dispatch_one(item: PendingDispatch) -> DispatchResult:
    # Celery runs this under asyncio.run() → fresh loop per call. Use the
    # NullPool celery factory so the connection is created and closed inside
    # the SAME loop (also safe from the API process: NullPool binds nothing).
    async with celery_session_factory() as session:
        dispatcher = NotificationDispatcher(session)
        return await dispatcher.dispatch(item)


async def dispatch_codes(items: list[PendingDispatch]) -> list[DispatchResult]:
    """Dispatch a batch of generated codes (called after Excel ingestion).

    One DB session and dispatcher per item; sends run concurrently.
    """
    results: list[DispatchResult] = []
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(_dispatch_one(item)) for item in items]
    for t in tasks:
        results.append(t.result())
    return results