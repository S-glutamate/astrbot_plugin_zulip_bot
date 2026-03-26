import zulip
import asyncio

from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import AstrBotMessage, PlatformMetadata
from astrbot.api.message_components import Plain, Image
from astrbot import logger

class ZulipEvent(AstrMessageEvent):
    def __init__(self, message_str: str, message_obj: AstrBotMessage, platform_meta: PlatformMetadata, session_id: str, client: zulip.Client):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.client = client

    def _get_topic(self) -> str:
        """提取话题名称，默认为 general"""
        topic = "general"
        raw = self.message_obj.raw_message
        if isinstance(raw, dict):
            topic = raw.get("subject") or raw.get("topic") or "general"
        return topic

    async def send(self, message: MessageChain):
        """
        发送消息到 Zulip。
        根据消息类型（群聊/私聊）构建正确的请求体。
        支持文本和图片（图片转为 URL 发送）。
        """
        # 合并消息链中的内容为字符串，Zulip 单次发送通常为一个内容块
        # 如果有图片，Zulip 通常期望 Markdown 格式的图片链接或直接上传，这里简化为发送文本描述或链接
        content_parts = []
        
        for comp in message.chain:
            if isinstance(comp, Plain):
                content_parts.append(comp.text)
            elif isinstance(comp, Image):
                # 如果是本地路径或 base64，Zulip API 直接发送较复杂，此处发送图片链接或提示
                # 假设 file 是可访问的 URL
                img_url = comp.file if isinstance(comp.file, str) and comp.file.startswith("http") else "[图片]"
                content_parts.append(f"![image]({img_url})")
        
        full_content = "\n".join(content_parts)
        
        if not full_content.strip():
            await super().send(message)
            return

        raw_msg = self.message_obj.raw_message
        is_stream = raw_msg.get("type") == "stream" if isinstance(raw_msg, dict) else False
        
        # 修改：显式声明字典类型，解决 Pylance 关于 update 重载匹配的报错
        request: dict = {
            "content": full_content,
        }

        if is_stream:
            # 群聊模式
            stream_name = self.message_obj.group_id
            if not stream_name:
                logger.error("尝试发送群聊消息但缺少 group_id (stream name)")
                return
            
            request.update({
                "type": "stream",
                "to": stream_name,
                "topic": self._get_topic()
            })
        else:
            # 私聊模式
            # 需要从原始消息或 session_id 反推接收者邮箱，或者依赖 AstrBot 的上下文
            # 这里通过 raw_message 获取发送者邮箱作为回复对象（私聊通常是双向的）
            sender_email = raw_msg.get("sender_email") if isinstance(raw_msg, dict) else None
            
            if not sender_email:
                # 极端情况下尝试从 session_id 映射，但通常私聊 session_id 是 user_id
                # 此处简化处理，假设私聊回复给原发送者
                logger.warning("无法确定私聊接收者邮箱，跳过发送")
                await super().send(message)
                return

            request.update({
                "type": "private",
                "to": [sender_email]
            })

        try:
            # 在线程池中执行同步请求，避免阻塞
            result = await asyncio.to_thread(self.client.send_message, request)
            logger.debug(f"Zulip 消息发送成功：{result}")
        except Exception as e:
            logger.error(f"Zulip 发送消息失败：{e}")
        
        # 调用父类 send 以完成事件流程（如记录日志等）
        await super().send(message)