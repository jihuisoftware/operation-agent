"""Retired terminal renderers cannot be revived through the shared RPC dispatcher."""
from gateway.rpc import server


def test_terminal_renderers_are_unavailable_without_affecting_liveness():
    for method in ("pet.cells", "learning.frames"):
        response = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": method, "params": {}})
        assert response["error"]["code"] == -32601
    assert server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "ping", "params": {}})["result"] == {"pong": True}
