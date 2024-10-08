import random
import time
import aiohttp
import asyncio
from utils import make_request, handle_error,insert_after
from telegram_handler import TelegramHandler
from loguru import logger
from colorama import init, Fore, Style
from cmd import print_s

class FarmBot:
    def __init__(self, client, platform):
        self.client = client
        self.platform = platform
        self.headers = self.gen_headers(self.platform)

    def gen_headers(self, platform):
        """Generates HTTP headers based on the platform."""
        ua = {
            "ios": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
            "android": "Mozilla/5.0 (Linux; Android 13; RMX3630 Build/TP1A.220905.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/125.0.6422.165 Mobile Safari/537.36",
        }
        headers = {
            "Accept-Language": "ru" if platform == "ios" else "ru,ru-RU;q=0.9,en-US;q=0.8,en;q=0.7",
            "Host": "qlyuker.io",
            "Locale": "ru",
            "Origin": "https://qlyuker.io",
            "Referer": "https://qlyuker.io/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "TGPlatform": ua[platform],
            "User-Agent": ua[platform],
        }
        if platform == "android":
            headers = insert_after(headers, "Referer", "sec-ch-ua", '"Android WebView";v="129", "Not=A?Brand";v="8", "Chromium";v="129"')
            headers = insert_after(headers, "sec-ch-ua", "sec-ch-ua-mobile", "?1")
            headers = insert_after(headers, "sec-ch-ua-mobile", "sec-ch-ua-platform", '"Android"')
            headers = insert_after(headers, "User-Agent", "X-Requested-With", "org.telegram.messenger")
        return headers

    async def login(self, query_id, session):
        """Handles login to the service using Telegram web data."""
        try:
            res = await make_request(session, "POST", "https://qlyuker.io/api/auth/start", {"startData": query_id}, "api/auth/start", self.headers)
            data = await res.json()

            if "user" not in data:
                logger.error(f"Failed to find user data in the response: {data}")
                return None

            return data
        except Exception as error:
            await handle_error(error, "", "getting Access Token")
            return None

    async def sync(self, url, payload, session):
        """Sends a sync request to the specified URL."""
        try:
            async with session.post(url, json=payload, headers=self.headers) as res:
                if res.status != 200:
                    logger.error(f"HTTP sync error: {res.status}. Response: {await res.text()}")
                    return None
                return await res.json()
        except Exception as e:
            logger.exception(f"Sync error: {e}")
            return None

    async def sync_gdata(self, session, current_energy, taps):
        """Synchronizes game data."""
        try:
            return await self.sync(
                "https://qlyuker.io/api/game/sync",
                {"clientTime": int(time.time()), "currentEnergy": current_energy, "taps": taps},
                session,
            )
        except Exception as e:
            logger.exception(f"Error syncing game data: {e}")
            return None

    async def sync_claim_daily(self, session):
        """Claims daily rewards."""
        try:
            return await self.sync("https://qlyuker.io/api/tasks/daily", {}, session)
        except Exception as e:
            logger.exception(f"Error claiming daily rewards: {e}")
            return None

    async def sync_upgrade(self, session, upgrade_id):
        """Attempts to buy an upgrade."""
        try:
            return await self.sync(
                "https://qlyuker.io/api/upgrades/buy",
                {"upgradeId": upgrade_id},
                session,
            )
        except Exception as e:
            logger.exception(f"Error buying upgrade: {e}")
            return None

    async def farming(self):
        """Main farming loop."""
        session_name = self.client.name
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                tg_handler = TelegramHandler(self.client, session_name, self.platform)
                tg_web_data, query_id = await tg_handler.get_tg_web_data()

                auth_data = await self.login(query_id, session)
                if not auth_data:
                    logger.error(f"Authorization error for {session_name}")
                    return

                current_energy = auth_data["user"]["currentEnergy"]
                max_energy = auth_data["user"]["maxEnergy"]
                coins_per_tap = auth_data["user"]["coinsPerTap"]
                energy_per_sec = auth_data["user"]["energyPerSec"]

                sleep_time = int(max_energy / energy_per_sec)
                while True:
                    # Sync the game data
                    sync_data = await self.sync_gdata(session, current_energy, 1)
                    if not sync_data:
                        logger.error(f"Sync error for {session_name}")
                        return

                    current_energy = sync_data["currentEnergy"]
                    taps = round(current_energy / coins_per_tap)
                    new_energy = max(0, current_energy - taps * coins_per_tap)

                    # Perform taps and update energy
                    sync_data = await self.sync_gdata(session, new_energy, taps)
                    if not sync_data:
                        logger.error(f"Sync error after tapping for {session_name}")
                        return
                    gained_coins = taps * coins_per_tap
                    print_s(f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.GREEN} OK {Style.RESET_ALL} | [{session_name}] | Success qlyuk! | Energy: [{Fore.RED if current_energy<=max_energy/10 else Fore.GREEN if current_energy>=max_energy/0.75 else Fore.YELLOW }{current_energy}{Style.RESET_ALL}/{Fore.YELLOW}{max_energy}{Style.RESET_ALL}] | Balance: {Fore.GREEN}{sync_data['currentCoins']}{Style.RESET_ALL} (+{Fore.GREEN}{gained_coins}{Style.RESET_ALL}) | Sleep {Fore.CYAN}{sleep_time}{Style.RESET_ALL}")
                    await asyncio.sleep(sleep_time)

        except Exception as e:
            logger.exception(f"Error during farming process for {session_name}: {e}")