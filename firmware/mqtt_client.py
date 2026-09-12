"""Self-contained MQTT 3.1.1 client with TLS for the edge gateway.

No umqtt dependency — packet encoding/decoding is done here so behaviour is
identical across MicroPython builds. Only QoS 1 publishing and QoS 1
subscriptions are used (at-least-once, matching the platform contract).

Device-only module (requires ``socket`` / ``ssl``).
"""

import json
import socket as _socket
import time

PROTOCOL_LEVEL = 4  # MQTT 3.1.1

# Packet types
_CONNECT = 0x10
_CONNACK = 0x20
_PUBLISH = 0x30
_PUBACK = 0x40
_SUBSCRIBE = 0x82
_SUBACK = 0x90
_PINGREQ = 0xC0
_PINGRESP = 0xD0
_DISCONNECT = 0xE0


def _encode_remaining_length(length: int) -> bytes:
    out = bytearray()
    while True:
        byte = length % 128
        length //= 128
        if length > 0:
            byte |= 0x80
        out.append(byte)
        if length == 0:
            return bytes(out)


def _encode_utf8(value: str) -> bytes:
    data = value.encode("utf-8")
    return len(data).to_bytes(2, "big") + data


class MqttError(OSError):
    pass


class EdgeMqttClient:
    def __init__(self, host: str, port: int, client_id: str, *,
                 username: str | None = None, password: str | None = None,
                 keepalive: int = 60, command_topic: str = "",
                 tls: bool = False, ca_path: str | None = None,
                 cert_path: str | None = None, key_path: str | None = None,
                 connect_timeout_s: float = 8.0):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.username = username
        self.password = password
        self.keepalive = keepalive
        self.command_topic = command_topic
        self.tls = tls
        self.ca_path = ca_path
        self.cert_path = cert_path
        self.key_path = key_path
        self.connect_timeout_s = connect_timeout_s
        self.sock = None
        self._callback = None
        self._pid = 0
        self.pong_received = True
        self.last_activity_s = 0.0

    @property
    def connected(self) -> bool:
        return self.sock is not None

    def set_callback(self, callback) -> None:
        self._callback = callback

    def _next_pid(self) -> int:
        self._pid = (self._pid % 65535) + 1
        return self._pid

    def _send(self, payload: bytes) -> None:
        self.sock.sendall(payload)
        self.last_activity_s = time.monotonic()

    def connect(self) -> None:
        if self.sock is not None:
            self.disconnect()

        sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        sock.settimeout(self.connect_timeout_s)
        sock.connect(_socket.getaddrinfo(self.host, self.port)[0][4])

        if self.tls:
            import ssl

            params = {"server_hostname": self.host, "cert_reqs": ssl.CERT_REQUIRED}
            if self.ca_path:
                try:
                    with open(self.ca_path, "r") as handle:
                        params["cadata"] = handle.read()
                except OSError:
                    params.pop("cadata", None)
            if self.cert_path and self.key_path:
                params["certfile"] = self.cert_path
                params["keyfile"] = self.key_path
            try:
                sock = ssl.wrap_socket(sock, **params)
            except TypeError:
                params.pop("cadata", None)
                sock = ssl.wrap_socket(sock, **params)

        sock.settimeout(self.connect_timeout_s)
        self.sock = sock
        try:
            self._send_connect()
            self._read_connack()
            if self.command_topic:
                self.subscribe(self.command_topic, qos=1)
            self.pong_received = True
            self.last_activity_s = time.monotonic()
        except Exception:
            self.disconnect()
            raise

    def _send_connect(self) -> None:
        flags = 0x02  # clean session
        if self.password is not None:
            flags |= 0x40
        if self.username is not None:
            flags |= 0x80
        variable = (
            _encode_utf8("MQTT")
            + bytes((PROTOCOL_LEVEL, flags))
            + self.keepalive.to_bytes(2, "big")
        )
        payload = _encode_utf8(self.client_id)
        if self.username is not None:
            payload += _encode_utf8(self.username)
        if self.password is not None:
            payload += _encode_utf8(self.password)
        body = variable + payload
        self._send(bytes((_CONNECT,)) + _encode_remaining_length(len(body)) + body)

    def _read_connack(self) -> None:
        packet = self._read_packet()
        if not packet or packet[0] != _CONNACK:
            raise MqttError("expected CONNACK")
        return_code = packet[2]
        if return_code != 0:
            raise MqttError("broker refused connection (code %d)" % return_code)

    def subscribe(self, topic: str, qos: int = 1) -> None:
        pid = self._next_pid()
        body = pid.to_bytes(2, "big") + _encode_utf8(topic) + bytes((qos,))
        self._send(bytes((_SUBSCRIBE,)) + _encode_remaining_length(len(body)) + body)

    def publish(self, topic: str, message, qos: int = 1) -> bool:
        if self.sock is None:
            return False
        if isinstance(message, (dict, list)):
            message = json.dumps(message, separators=(",", ":"))
        if isinstance(message, str):
            message = message.encode("utf-8")
        packet = bytes((_PUBLISH | (qos << 1),))
        body = _encode_utf8(topic)
        if qos:
            body += self._next_pid().to_bytes(2, "big")
        body += message
        self._send(packet + _encode_remaining_length(len(body)) + body)
        if qos:
            self._wait_puback()
        return True

    def _wait_puback(self) -> None:
        deadline = time.monotonic() + self.connect_timeout_s
        while time.monotonic() < deadline:
            packet = self._read_packet()
            if packet is None:
                time.sleep_ms(5)
                continue
            if packet[0] == _PUBACK:
                return
            self._dispatch(packet)

    def ping(self) -> None:
        self._send(bytes((_PINGREQ, 0x00)))

    def _read_packet(self):
        try:
            header = self.sock.recv(1)
        except (_socket.timeout, OSError):
            return None
        if not header:
            raise MqttError("connection lost")
        remaining = 0
        multiplier = 1
        while True:
            byte = self.sock.recv(1)
            if not byte:
                raise MqttError("connection lost")
            remaining += (byte[0] & 0x7F) * multiplier
            if not byte[0] & 0x80:
                break
            multiplier *= 128
        body = bytearray()
        while len(body) < remaining:
            chunk = self.sock.recv(remaining - len(body))
            if not chunk:
                raise MqttError("connection lost")
            body.extend(chunk)
        return bytes((header[0],)) + bytes(body)

    def _read_uint16(self, data, offset):
        return (data[offset] << 8) | data[offset + 1], offset + 2

    def _dispatch(self, packet: bytes) -> None:
        packet_type = packet[0] & 0xF0
        offset = 2
        if packet_type == _PUBLISH:
            topic_len, offset = self._read_uint16(packet, offset)
            topic = packet[offset:offset + topic_len].decode("utf-8")
            offset += topic_len
            qos = (packet[0] >> 1) & 0x03
            if qos > 0:
                _, offset = self._read_uint16(packet, offset)
            payload = packet[offset:].decode("utf-8", errors="replace")
            if qos == 1:
                self._send_puback(packet[2], packet[3])
            if self._callback is not None:
                self._callback(topic, payload)
        elif packet_type == _PINGRESP:
            self.pong_received = True
        elif packet_type == _SUBACK:
            pass

    def _send_puback(self, hi: int, lo: int) -> None:
        self._send(bytes((_PUBACK, 0x02, hi, lo)))

    def poll(self, timeout_ms: int = 0) -> None:
        if self.sock is None:
            return
        if timeout_ms > 0:
            sock = self.sock
            previous = sock.gettimeout()
            sock.settimeout(timeout_ms / 1000.0)
            try:
                self._poll_once()
            finally:
                sock.settimeout(previous)
        else:
            self._poll_once()

    def _poll_once(self) -> None:
        try:
            packet = self._read_packet()
        except (_socket.timeout, OSError):
            return
        if packet is not None:
            self._dispatch(packet)

    def idle_for_s(self) -> float:
        if self.sock is None:
            return 0.0
        return time.monotonic() - self.last_activity_s

    def disconnect(self) -> None:
        if self.sock is None:
            return
        try:
            self._send(bytes((_DISCONNECT, 0x00)))
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass
        self.sock = None