"""API-server reasoning-effort request parsing accepts the full ladder.

_request_reasoning_config() previously whitelisted only none..xhigh, so an
API/browser client sending ``max`` or ``ultra`` (both valid /reasoning and
config.yaml levels) was silently ignored and the session ran at the default
effort. The server now accepts the full internal ladder; per-provider wire
clamping happens downstream in the transports/profiles via
agent.reasoning_effort (#78216's api_server observation).
"""

from gateway.session_model_options import _request_reasoning_config
from hermes_constants import VALID_REASONING_EFFORTS


class TestRequestReasoningFullLadder:
    def test_every_configurable_level_is_accepted(self):
        for level in VALID_REASONING_EFFORTS:
            out = _request_reasoning_config({"reasoning_effort": level})
            assert out == {"enabled": True, "effort": level}, level

    def test_none_disables(self):
        assert _request_reasoning_config({"reasoning_effort": "none"}) == {
            "enabled": False
        }

    def test_structured_object_shape(self):
        out = _request_reasoning_config(
            {"reasoning": {"enabled": True, "effort": "ultra"}}
        )
        assert out == {"enabled": True, "effort": "ultra"}

    def test_unknown_level_still_ignored(self):
        assert _request_reasoning_config({"reasoning_effort": "turbo"}) is None


def test_service_tier_preserves_missing_and_explicit_disable():
    from gateway.session_model_options import _REQUEST_OPTION_MISSING, _request_service_tier

    assert _request_service_tier({}) is _REQUEST_OPTION_MISSING
    assert _request_service_tier({"fast": "false"}) is None
    assert _request_service_tier({"fast": "true"}) == "priority"
    assert _request_service_tier({"fast": True, "service_tier": None}) is None
    assert _request_service_tier({"service_tier": " default "}) == "default"
