"""In-memory delivery transport for heartbeat ownership contracts."""
from gateway.platforms.base import BasePlatformAdapter, SendResult


class WireAdapter(BasePlatformAdapter):
    async def connect(self, *, is_reconnect=False):
        return True

    async def disconnect(self):
        pass

    async def get_chat_info(self, chat_id):
        return {}

    async def send(self, chat_id, content, reply_to=None, metadata=None):
        self.wire.append(content)
        return SendResult(success=True, message_id=str(len(self.wire)))

