"""Sensor register decode and unit conversion.

Converts raw Modbus register values into the units the ingestion pipeline expects:
pressure in **bar**, temperature in **°C**, status as an integer bitmask.

Channel configs are plain dicts, e.g.::

    "pressure": {
        "registers": [0, 1],          # register indices (within the polled block)
        "endian": "big",              # u32 assembly
        "kind": "level_mm",           # what the raw value represents
        "scale": 1.0,
        "offset": 0.0,
        "density_kg_m3": 750.0,       # gasoline default
    }
"""

from modbus_rtu import assemble_u32

G_COMPONENT = 9.80665
PA_PER_BAR = 100000.0
GASOLINE_KG_M3 = 750.0


class SensorRead:
    __slots__ = ("pressure_bar", "temperature_c", "status", "errors")

    def __init__(self, pressure_bar=None, temperature_c=None, status=0, errors=()):
        self.pressure_bar = pressure_bar
        self.temperature_c = temperature_c
        self.status = status
        self.errors = tuple(errors)


def norm_channel(channel: dict | None) -> dict:
    channel = dict(channel or {})
    channel.setdefault("scale", 1.0)
    channel.setdefault("offset", 0.0)
    channel.setdefault("registers", [0])
    return channel


def pressure_bar_from_raw(raw: float, channel: dict) -> float:
    kind = channel.get("kind", "bar")
    value = raw * channel.get("scale", 1.0) + channel.get("offset", 0.0)
    if kind in ("mbar", "hpa"):
        return value / 1000.0
    if kind == "bar":
        return value
    if kind in ("level_mm", "mm"):
        density = channel.get("density_kg_m3", GASOLINE_KG_M3)
        meters = value / 1000.0
        return meters * density * G_COMPONENT / PA_PER_BAR
    if kind in ("level_cm", "cm"):
        density = channel.get("density_kg_m3", GASOLINE_KG_M3)
        meters = value / 100.0
        return meters * density * G_COMPONENT / PA_PER_BAR
    raise ValueError("unknown pressure kind %r" % kind)


def temperature_c_from_raw(raw: float, channel: dict) -> float:
    kind = channel.get("kind", "raw")
    value = raw * channel.get("scale", 1.0) + channel.get("offset", 0.0)
    if kind in ("raw", "c", "degc"):
        return value
    if kind in ("c_1e1", "decidegrees"):
        return value / 10.0
    if kind in ("c_1e2", "centidegrees"):
        return value / 100.0
    raise ValueError("unknown temperature kind %r" % kind)


def _channel_value(regs: list[int], channel: dict, endian_default: str = "big"):
    channel = norm_channel(channel)
    indices = channel.get("registers", [0])
    picked = []
    for idx in indices:
        if not 0 <= idx < len(regs):
            return None
        picked.append(regs[idx])
    if len(picked) == 1:
        return picked[0]
    return assemble_u32(picked, channel.get("endian", endian_default))


def decode_registers(regs: list[int], sensor_cfg: dict) -> SensorRead:
    """Decode one polled register block into platform units."""
    errors = []
    pressure_channel = norm_channel(sensor_cfg.get("pressure"))
    pressure_raw = _channel_value(regs, pressure_channel, "big")
    pressure_bar = None
    if pressure_raw is not None:
        try:
            pressure_bar = pressure_bar_from_raw(pressure_raw, pressure_channel)
        except ValueError as exc:
            errors.append("pressure: %s" % exc)

    temperature_c = None
    temp_channel = sensor_cfg.get("temperature")
    if temp_channel:
        temp_raw = _channel_value(regs, norm_channel(temp_channel), "big")
        if temp_raw is not None:
            try:
                temperature_c = temperature_c_from_raw(temp_raw, norm_channel(temp_channel))
            except ValueError as exc:
                errors.append("temperature: %s" % exc)

    status = 0
    status_channel = sensor_cfg.get("status")
    if status_channel:
        status_raw = _channel_value(regs, norm_channel(status_channel), "big")
        if status_raw is not None:
            status = status_raw & int(status_channel.get("mask", 0xFFFF))

    return SensorRead(pressure_bar=pressure_bar, temperature_c=temperature_c,
                      status=status, errors=errors)