"""Desktop's backend no longer configures messaging accounts or grants bot access."""

from fastapi.testclient import TestClient


def test_messaging_and_pairing_are_unavailable_on_the_shared_backend():
    from hermes_cli.web_server import _SESSION_TOKEN, app

    client = TestClient(app, headers={"X-Hermes-Session-Token": _SESSION_TOKEN})
    for method, path in (
        ("GET", "/api/messaging/platforms"),
        ("PUT", "/api/messaging/platforms/telegram"),
        ("POST", "/api/messaging/telegram/onboarding/start"),
        ("GET", "/api/pairing"),
        ("POST", "/api/pairing/approve"),
    ):
        assert client.request(method, path, json={}).status_code == 404
    # An ordinary backend API still responds through the same authenticated app.
    assert client.get("/api/dashboard/themes").status_code == 200
