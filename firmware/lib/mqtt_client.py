"""TLS MQTT client for ESP32-S3."""
import ujson
import time
import gc


class MQTTClient:
    """MQTT client with TLS support for ESP32-S3 MicroPython."""

    def __init__(self, client_id, server, port=8883, ssl=True, ssl_params=None,
                 keepalive=60, max_reconnect_delay=300, topic_prefix="fuel",
                 max_buffered=50):
        self.client_id = client_id
        self.server = server
        self.port = port
        self.ssl = ssl
        self.ssl_params = ssl_params or {}
        self.keepalive = keepalive
        self.topic_prefix = topic_prefix
        self.connected = False
        self._buffer = []
        self._max_buffered = max_buffered
        self._command_handler = None
        self._reconnect_delay = 5
        self._max_reconnect_delay = max_reconnect_delay
        self._reset_requested = False
        self._client = None

        try:
            from umqtt.simple import MQTTClient as _MQTTClient
            self._client = _MQTTClient(
                client_id, server, port=port,
                ssl=ssl, ssl_params=ssl_params
            )
            self._client.set_callback(self._on_message)
        except ImportError:
            self._client = None

    def set_command_handler(self, handler):
        self._command_handler = handler

    def _on_message(self, topic, msg):
        try:
            topic_str = topic.decode('utf-8')
            payload = ujson.loads(msg.decode('utf-8'))
            if self._command_handler:
                result = self._command_handler.execute_from_mqtt(topic_str, payload)
                resp_topic = topic_str.replace("/cmd", "/resp")
                self._safe_publish(resp_topic, ujson.dumps(result), qos=1)
        except Exception as e:
            pass

    def _safe_publish(self, topic, payload, qos=0, retain=False):
        try:
            if self._client and self.connected:
                self._client.publish(topic, payload.encode('utf-8'), qos=qos, retain=retain)
        except Exception:
            self.connected = False
            if len(self._buffer) < self._max_buffered:
                self._buffer.append((topic, payload, qos, retain))

    def connect(self):
        if not self._client:
            raise OSError("MQTT client library not available")
        self._client.connect()
        self.connected = True
        self._reconnect_delay = 5

        self._client.subscribe("%s/%s/cmd" % (self.topic_prefix, self.client_id))
        self._client.subscribe("%s/%s/config" % (self.topic_prefix, self.client_id))

        self._client.publish(
            "%s/%s/status" % (self.topic_prefix, self.client_id),
            ujson.dumps({"status": "online", "ts": int(time.time())}),
            qos=1, retain=True
        )

    def reconnect(self):
        try:
            self._client.disconnect()
        except Exception:
            pass
        self.connected = False
        time.sleep(self._reconnect_delay)
        self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)
        self.connect()

    def disconnect(self):
        if self._client:
            try:
                self._client.disconnect()
            except Exception:
                pass
        self.connected = False

    def publish(self, topic, payload, qos=0, retain=False):
        if not self.connected:
            raise OSError("Not connected to MQTT broker")
        self._client.publish(topic, payload.encode('utf-8'), qos=qos, retain=retain)

    def drain_buffer(self):
        gc.collect()
        failed = []
        while self._buffer and self.connected:
            topic, payload, qos, retain = self._buffer.pop(0)
            try:
                self._client.publish(topic, payload.encode('utf-8'), qos=qos, retain=retain)
            except Exception:
                failed.append((topic, payload, qos, retain))
                self.connected = False
                break
        self._buffer = failed

    def loop(self):
        if self._client and self.connected:
            try:
                self._client.check_msg()
            except Exception:
                self.connected = False

    def is_connected(self):
        return self.connected

    def request_reset(self):
        self._reset_requested = True

    def should_reset(self):
        return self._reset_requested
