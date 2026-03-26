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
    "e-mail": "你的机器人的 Zulip 账号邮箱",
    "api_key": "你的机器人的 Zulip API Key",
    "site": "你的 Zulip 站点网址，例如 https://yourdomain.zulipchat.com"
})
class ZulipPlatformAdapter(Platform):
    def __init__(self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue) -> None:
        super().__init__(platform_config, event_queue)
        self.config = platform_config
        self.settings = platform_settings
        # 新增：存储机器人自身的 ID (邮箱)
        self.bot_email = platform_config.get('e-mail', '')

    async def send_by_session(self, session: MessageSesion, message_chain: MessageChain):
        await super().send_by_session(session, message_chain)

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="zulip",
            description="Zulip 聊天平台适配",
            id="zulip"
        )

    async def run(self):
        async def on_message(event):
            if event["type"] == "message":
                msg = event["message"]
                # 过滤掉机器人自己发出的消息，防止死循环
                if str(msg.get("sender_email", "")) == self.bot_email:
                    return
                
                logger.debug(f"收到 Zulip 消息：{msg.get('content', '')[:50]}...")
                abm = await self.convert_message(msg)
                logger.debug(f"消息转换完成，session_id: {abm.session_id}, self_id: {abm.self_id}")
                await self.handle_msg(abm)

        self.client = zulip.Client(
            email=self.config['e-mail'],
            api_key=self.config['api_key'],
            site=self.config['site']
        )
        
        response = self.client.register(event_types=["message"])
        queue_id = response["queue_id"]
        last_event_id = response["last_event_id"]
        logger.info("Zulip 监听启动...")
        
        while True:
            try:
                events = await asyncio.wait_for(
                    asyncio.to_thread(self.client.get_events, queue_id=queue_id, last_event_id=last_event_id),
                    timeout=60.0
                )
                
                for event in events.get("events", []):
                    await on_message(event)
                    last_event_id = event["id"]
                    
            except asyncio.TimeoutError:
                logger.warning("Zulip get_events 超时，重试中...")
                continue
            except Exception as e:
                logger.error(f"Zulip 监听出错：{e}")
                await asyncio.sleep(5)

    async def convert_message(self, msg: dict) -> AstrBotMessage:
        abm = AstrBotMessage()
        is_stream = msg.get("type") == "stream"
        abm.type = MessageType.GROUP_MESSAGE if is_stream else MessageType.FRIEND_MESSAGE
        
        # 群聊需要记录流名称，私聊为 None
        abm.group_id = msg.get("display_recipient") if is_stream else None
        
        abm.message_str = msg.get("content", "")
        abm.sender = MessageMember(user_id=str(msg.get("sender_id")), nickname=msg.get("sender_full_name", ""))
        abm.message = [Plain(text=msg.get("content", ""))]
        abm.raw_message = msg
        
        # 修正：self_id 必须严格为机器人标识
        abm.self_id = self.bot_email
        
        # 修正：session_id 生成逻辑
        # 群聊：stream:topic 确保不同话题不混淆
        # 私聊：sender_id 确保单人会话
        if is_stream:
            topic = msg.get("subject", "general")
            stream_name = msg.get("display_recipient", "unknown")
            abm.session_id = f"{stream_name}:{topic}"
        else:
            abm.session_id = str(msg.get("sender_id"))
            
        abm.message_id = str(msg.get("id"))
        logger.debug(f"转换后的消息对象：type={abm.type}, group_id={abm.group_id}, session_id={abm.session_id}")
        return abm

    async def handle_msg(self, message: AstrBotMessage):
        logger.info(f"准备处理消息：{message.message_str[:30]}...")
        message_event = ZulipEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            client=self.client
        )
        self.commit_event(message_event)
        logger.debug("消息事件已提交到队列")