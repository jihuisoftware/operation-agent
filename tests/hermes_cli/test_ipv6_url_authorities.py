"""IPv6 binds must render as bracketed URL authorities everywhere a URL is built.

An IPv6 literal followed by ``:port`` is only a valid URL authority inside
brackets (``http://[::1]:9119``); unbracketed ``http://::1:9119`` is not a URL a
browser or ``urllib`` can parse. Covers the backend attach URL, the
headless startup path, and the shared host formatter
(#67367).
"""
import contextlib
import types

import pytest
import uvicorn

from hermes_cli import main_dashboard, web_server


def _stub_uvicorn(monkeypatch):
    """Replace uvicorn.Config/Server with no-op fakes so start_server returns."""
    captured: dict = {}

    class _FakeConfig:
        loaded = True
        host = "127.0.0.1"
        port = 8000
        _loop_factory = None

        def __init__(self, *args, **kwargs):
            captured.update(kwargs)

        def load(self):
            pass

        def get_loop_factory(self):
            return self._loop_factory

        class lifespan_class:
            should_exit = False
            state: dict = {}

            def __init__(self, *a, **kw):
                pass

            async def startup(self):
                pass

            async def shutdown(self):
                pass

    class _FakeServer:
        should_exit = False
        started = True
        servers: list = []
        lifespan = None

        @staticmethod
        def capture_signals():
            return contextlib.nullcontext()

        async def startup(self, sockets=None):
            pass

        async def main_loop(self):
            pass

        async def shutdown(self, sockets=None):
            pass

    monkeypatch.setattr(uvicorn, "Config", _FakeConfig)
    monkeypatch.setattr(uvicorn, "Server", lambda config: _FakeServer())
    return captured


class TestFormatUrlHost:

    def test_brackets_ipv6_literal_with_port_following(self):
        from hermes_cli.url_utils import format_url_host

        assert format_url_host("::1") == "[::1]"
        assert format_url_host("fe80::1") == "[fe80::1]"

    def test_preserves_ipv4_and_names(self):
        from hermes_cli.url_utils import format_url_host

        assert format_url_host("127.0.0.1") == "127.0.0.1"
        assert format_url_host("localhost") == "localhost"

    def test_already_bracketed_stays_bracketed(self):
        from hermes_cli.url_utils import format_url_host

        assert format_url_host("[::1]") == "[::1]"

    def test_escapes_ipv6_zone_identifier(self):
        from hermes_cli.url_utils import format_url_host

        assert format_url_host("fe80::1%eth0") == "[fe80::1%25eth0]"
        assert format_url_host("[fe80::1%eth0]") == "[fe80::1%25eth0]"


class TestBackendStartup:

    def test_start_server_preserves_ipv6_bind_without_opening_a_browser(self, monkeypatch):
        import webbrowser

        config = _stub_uvicorn(monkeypatch)
        opened = []
        monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url))

        web_server.start_server(host="::1", port=9119, open_browser=True)

        assert config["host"] == "::1"
        assert opened == []


class TestAttachUrl:

    def test_attach_reports_ipv6_host_without_opening_a_browser(self, monkeypatch, capsys):
        """Desktop backend attachment reports a valid URL without browser navigation."""
        import webbrowser
        from gateway import host_rendezvous as hr

        opened = []
        monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url))
        record = types.SimpleNamespace(host="::1", port=9119, pid=4242, role="dashboard")
        monkeypatch.setattr(main_dashboard, "_host_backend_attachment", lambda: record)
        monkeypatch.setattr(main_dashboard, "_is_desktop_owned_backend", lambda: False)
        monkeypatch.setattr(main_dashboard, "_explicit_endpoint_flags", lambda: set())
        monkeypatch.setattr(hr, "probe_owner", lambda _r: {"servesSpa": True, "pid": 4242})
        monkeypatch.setattr(
            "hermes_cli.profiles.get_active_profile_name", lambda: "worker_x"
        )

        args = types.SimpleNamespace(
            host="::1", port=9119, no_open=False, isolated=False, open_profile=""
        )
        with pytest.raises(SystemExit) as exc:
            main_dashboard._attach_to_host_backend(args)

        assert exc.value.code == 0
        assert opened == []
        assert "http://[::1]:9119/?profile=worker_x" in capsys.readouterr().out
