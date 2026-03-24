import asyncio
import zulip

from astrbot.api.platform import Platform, AstrBotMessage, MessageMember, PlatformMetadata, MessageType
from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain, Image
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.api.platform import register_platform_adapter
from astrbot import logger
from .zulip_event import ZulipEvent

@register_platform_adapter("zulip", "Zulip 平台适配器", default_config_tmpl={
    "config_file": "zuliprc"
})
class ZulipPlatformAdapter(Platform):
    def __init__(self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue) -> None:
        super().__init__(platform_config, event_queue)
        self.config = platform_config
        self.settings = platform_settings

    async def send_by_session(self, session: MessageSesion, message_chain: MessageChain):
        await super().send_by_session(session, message_chain)

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="zulip",
            description="Zulip 聊天平台适配",
            id="zulip"
        )

    async def run(self):
        def on_message(event):
            if event["type"] == "message":
                msg = event["message"]
                abm = asyncio.run(self.convert_message(msg))
                asyncio.run(self.handle_msg(abm))

        self.client = zulip.Client(config_file=self.config.get("config_file", "zuliprc"))
        response = self.client.register(event_types=["message"])
        queue_id = response["queue_id"]
        last_event_id = response["last_event_id"]
        logger.info("Zulip 监听启动...")
        while True:
            events = self.client.get_events(queue_id=queue_id, last_event_id=last_event_id)
            for event in events["events"]:
                on_message(event)
                last_event_id = event["id"]
            await asyncio.sleep(1)

    async def convert_message(self, msg: dict) -> AstrBotMessage:
        abm = AstrBotMessage()
        abm.type = MessageType.GROUP_MESSAGE if msg.get("type") == "stream" else MessageType.FRIEND_MESSAGE
        abm.group_id = msg.get("display_recipient") if msg.get("type") == "stream" else None
        abm.message_str = msg.get("content", "")
        abm.sender = MessageMember(user_id=str(msg.get("sender_id")), nickname=msg.get("sender_full_name", ""))
        abm.message = [Plain(text=msg.get("content", ""))]
        abm.raw_message = msg
        abm.self_id = str(msg.get("sender_id"))
        abm.session_id = str(msg.get("sender_id"))
        abm.message_id = str(msg.get("id"))
        return abm

    async def handle_msg(self, message: AstrBotMessage):
        message_event = ZulipEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            client=self.client
        )
        self.commit_event(message_event)
