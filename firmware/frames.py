"""MQTT frame builders.

Emit exactly the JSON shapes the ingestion consumers expect (see
``docs/mqtt-protocol.md``). Never emit ``None`` values; unknown frames are the
consumer's problem, malformed ones are ours.
"""


def _drop_none(payload: dict) -> dict:
    return {key: value for key, value in payload.items() if value is not None}


def build_reading(gateway_mac: str, sensor_serial: str, pressure_bar: float,
                  temperature_c=None, status: int = 0, timestamp=None) -> dict:
    """Tank sensor reading → ``fuel/<mac>/readings`` frame."""
    if pressure_bar is None:
        raise ValueError("pressure is mandatory")
    measurement = {
        "timestamp": timestamp,
        "pressure": pressure_bar,
        "temperature": temperature_c,
        "status": int(status),
    }
    return _drop_none({
        "gateway_mac": gateway_mac,
        "sensor_serial_number": sensor_serial,
        "measurement": _drop_none(measurement),
    })


def build_status(gateway_mac: str, firmware_version: str, status: str = "online",
                 uptime_s=None, rssi=None, reset_cause=None, timestamp=None) -> dict:
    """Heartbeat → ``fuel/<mac>/status`` frame."""
    return _drop_none({
        "status": status,
        "firmware_version": firmware_version,
        "timestamp": timestamp,
        "uptime_s": uptime_s,
        "rssi_dbm": rssi,
        "reset_cause": reset_cause,
    })


def build_ack(command_id: str, status: str, detail: str = None) -> dict:
    """Command reply → ``fuel/<mac>/command/ack`` frame."""
    if status not in ("executed", "rejected"):
        raise ValueError("ack status must be 'executed' or 'rejected'")
    return _drop_none({
        "command_id": command_id,
        "status": status,
        "detail": detail,
    })