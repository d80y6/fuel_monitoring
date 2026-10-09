"""Configuration fails closed in production.

Before this, a production deployment could start with plaintext broker
credentials, a placeholder signing key and debug logging, and nothing would say
so until an audit. Startup is the only moment these mistakes are cheap to fix, so
the process refuses to come up instead.
"""

from __future__ import annotations

import pytest

from fmp.core.config import Settings

GOOD = {
    "ENVIRONMENT": "prod",
    "SECRET_KEY": "b" * 64,
    "POSTGRES_PASSWORD": "a-real-password",
    "MQTT_USE_TLS": True,
    "MQTT_CA_CERT": "/opt/emqx/etc/certs/ca.pem",
}


def prod_settings(**overrides):
    params = {**GOOD, **overrides}
    return Settings(**params)


def test_production_refuses_plaintext_mqtt():
    with pytest.raises(ValueError, match="MQTT_USE_TLS"):
        prod_settings(MQTT_USE_TLS=False, MQTT_CA_CERT=None)


def test_production_refuses_placeholder_secret_key():
    for placeholder in ("change-me", "changeme", "dev-secret", "secret"):
        with pytest.raises(ValueError, match="SECRET_KEY"):
            prod_settings(SECRET_KEY=placeholder)


def test_production_refuses_empty_database_password():
    with pytest.raises(ValueError, match="POSTGRES_PASSWORD"):
        prod_settings(POSTGRES_PASSWORD="")


def test_production_refuses_debug_logging():
    with pytest.raises(ValueError, match="DEBUG"):
        prod_settings(DEBUG=True)


def test_production_error_lists_every_problem_at_once():
    """An operator should not have to fix one problem per restart."""
    with pytest.raises(ValueError) as excinfo:
        prod_settings(
            MQTT_USE_TLS=False, MQTT_CA_CERT=None, SECRET_KEY="change-me", DEBUG=True
        )
    message = str(excinfo.value)
    assert "MQTT_USE_TLS" in message
    assert "SECRET_KEY" in message
    assert "DEBUG" in message


def test_secure_production_configuration_starts():
    settings = prod_settings()
    assert settings.ENVIRONMENT == "prod"
    assert settings.MQTT_USE_TLS is True


def test_dev_and_test_are_unaffected():
    """Local development must not be forced to generate certificates."""
    assert Settings(ENVIRONMENT="dev").MQTT_USE_TLS is False
    assert Settings(ENVIRONMENT="test").MQTT_USE_TLS is False


def test_tls_port_is_used_only_when_tls_is_on(monkeypatch):
    """Connecting to 8883 while sending plaintext there would be a silent bug.

    ``_broker_port`` reads the process-wide settings singleton, so the module
    attribute is patched rather than constructing a throwaway Settings.
    """
    from fmp.ingestion import main as ing

    plaintext = Settings(ENVIRONMENT="dev", MQTT_PORT=1883, MQTT_TLS_PORT=8883)
    assert plaintext.MQTT_TLS_PORT == 8883, "TLS port is configured but unused"
    monkeypatch.setattr(ing, "settings", plaintext)
    assert ing._broker_port() == 1883

    secured = Settings(ENVIRONMENT="dev", MQTT_PORT=1883, MQTT_TLS_PORT=8883, MQTT_USE_TLS=True)
    monkeypatch.setattr(ing, "settings", secured)
    assert ing._broker_port() == 8883


def test_tls_enabled_without_a_ca_refuses_to_start(monkeypatch):
    """A half-configured TLS setup must fail, not silently use plaintext."""
    from fmp.ingestion import main as ing

    broken = Settings(
        ENVIRONMENT="dev", MQTT_PORT=1883, MQTT_TLS_PORT=8883,
        MQTT_USE_TLS=True, MQTT_CA_CERT=None,
    )
    monkeypatch.setattr(ing, "settings", broken)
    with pytest.raises(RuntimeError, match="refusing to fall back to plaintext"):
        ing._build_client()