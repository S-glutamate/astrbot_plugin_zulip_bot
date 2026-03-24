from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import AstrBotMessage, PlatformMetadata
from astrbot.api.message_components import Plain, Image
from .client import FakeClient
from astrbot.core.utils.io import download_image_by_url

class Zulip_Event(AstrMessageEvent):
    def __init__(self, message_str: str, message_obj: AstrBotMessage, platform_meta: PlatformMetadata, session_id: str, client: FakeClient):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.client = client
        
    async def send(self, message: MessageChain):
        for i in message.chain: # 遍历消息链
            if isinstance(i, Plain): # 如果是文字类型的
                await self.client.send_text(to=self.get_sender_id(), message=i.text)
            elif isinstance(i, Image): # 如果是图片类型的 
                img_url = i.file
                img_path = ""
                # 下面的三个条件可以直接参考一下。
                if img_url.startswith("file:///"):
                    img_path = img_url[8:]
                elif i.file and i.file.startswith("http"):
                    img_path = await download_image_by_url(i.file)
                else:
                    img_path = img_url

                # 请善于 Debug！
                    
                await self.client.send_image(to=self.get_sender_id(), image_path=img_path)

        await super().send(message) # 需要最后加上这一段，执行父类的 send 方法。