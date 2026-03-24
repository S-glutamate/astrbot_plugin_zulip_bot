import zulip
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import AstrBotMessage, PlatformMetadata
from astrbot.api.message_components import Plain, Image

class ZulipEvent(AstrMessageEvent):
    def __init__(self, message_str: str, message_obj: AstrBotMessage, platform_meta: PlatformMetadata, session_id: str, client: zulip.Client):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.client = client

    async def send(self, message: MessageChain):
        # 只支持文本和图片
        for i in message.chain:
            if isinstance(i, Plain):
                # 发送文本消息
                topic = None
                raw = self.message_obj.raw_message
                if isinstance(raw, dict):
                    topic = raw.get("subject") or raw.get("topic")
                if not topic:
                    topic = "general"
                request = {
                    "type": "stream",
                    "to": self.message_obj.group_id or self.message_obj.session_id,
                    "topic": topic,
                    "content": i.text
                }
                self.client.send_message(request)
            elif isinstance(i, Image):
                # 发送图片（Zulip 仅支持图片 url，或可上传图片，简化为发送 url）
                img_url = i.file
                topic = None
                raw = self.message_obj.raw_message
                if isinstance(raw, dict):
                    topic = raw.get("subject") or raw.get("topic")
                if not topic:
                    topic = "general"
                request = {
                    "type": "stream",
                    "to": self.message_obj.group_id or self.message_obj.session_id,
                    "topic": topic,
                    "content": img_url
                }
                self.client.send_message(request)
        await super().send(message)