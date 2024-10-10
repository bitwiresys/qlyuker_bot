import asyncio
from pyrogram import Client
from pyrogram.raw.functions.messages import RequestWebView
from pyrogram.errors import FloodWait, Unauthorized, UserDeactivated, AuthKeyUnregistered
from urllib.parse import unquote, urlparse, parse_qs
from loguru import logger


class TelegramHandler:
    def __init__(self, client: Client, session_name: str, platform: str):
        self.client = client
        self.session_name = session_name
        self.platform = platform

    async def get_tg_web_data(self):
        """Fetches Telegram web data needed for authentication."""
        try:
            if not self.client.is_connected:
                try:
                    await self.client.connect()
                except (Unauthorized, UserDeactivated, AuthKeyUnregistered):
                    logger.error(f"{self.session_name} | Authorization failed")
                    return None, None

            while True:
                try:
                    peer = await self.client.resolve_peer("qlyukerbot")
                    break
                except FloodWait as fl:
                    logger.warning(f"{self.session_name} | FloodWait {fl}")
                    await asyncio.sleep(fl.value * 2)

            web_view = await self.client.invoke(
                RequestWebView(
                    peer=peer,
                    bot=peer,
                    platform=self.platform,
                    from_bot_menu=False,
                    url="https://qlyuker.io/",
                )
            )

            auth_url = web_view.url
            tg_web_data = unquote(
                auth_url.split("tgWebAppData=", maxsplit=1)[1].split("&tgWebAppVersion", maxsplit=1)[0]
            )
            query_id = parse_qs(urlparse(web_view.url).fragment).get("tgWebAppData", [None])[0]

            if self.client.is_connected:
                await self.client.disconnect()

            return tg_web_data, query_id

        except FloodWait as fl:
            logger.warning(f"{self.session_name} | FloodWait {fl}")
            await asyncio.sleep(fl.value * 2)

        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error while getting Tg Web Data: {error}")
            await asyncio.sleep(3)
            return None, None