import random
import time
import aiohttp
import asyncio
from utils import make_request, handle_error, insert_after, load_config
from telegram_handler import TelegramHandler
from loguru import logger
from colorama import init, Fore, Style

# Load configurations from the .conf file
config = load_config()

# Extract log settings from the configuration
TAP_COUNT = config.getint("bot", "tap_count") if config.get("bot", "tap_count") != '' else 0
RANDOM_TAP_COUNT = config.get("bot", "random_tap_count") if config.get("bot", "random_tap_count") != '' else 0
SLEEP_PER_TAP = config.getint("bot", "sleep_per_tap") if config.get("bot", "sleep_per_tap") != '' else 0
RANDOM_SLEEP_PER_TAP = config.get("bot", "random_sleep_per_tap") if config.get("bot", "random_sleep_per_tap") != '' else 0
MIN_SAVE_ENERGY = config.getint("bot", "min_save_energy") if config.get("bot", "min_save_energy") != '' else 0
MIN_SAVE_BALANCE = config.getint("bot", "min_save_balance") if config.get("bot", "min_save_balance") != '' else 0
USE_AUTO_UPGRADES = config.getboolean("bot", "use_auto_upgrades") if config.get("bot", "use_auto_upgrades") != '' else True
MAX_UPGRADE_LVL = config.getint("bot", "max_upgrade_lvl") if config.get("bot", "max_upgrade_lvl") != '' else 0
MAX_UPGRADE_COST = config.getint("bot", "max_upgrade_cost") if config.get("bot", "max_upgrade_cost") != '' else 0
MIN_UPGRADE_PROFIT = config.getint("bot", "min_upgrade_profit") if config.get("bot", "min_upgrade_profit") != '' else 0
USE_DAILY_ENERGY = config.getboolean("bot", "use_daily_energy") if config.get("bot", "use_daily_energy") != '' else True

class FarmBot:
    def __init__(self, client, platform):
        self.client = client
        self.platform = platform
        self.headers = self.gen_headers(self.platform)

    def gen_energy_line(self,current,max,min_percent,max_percent):
        return f"[{Fore.RED if current<=max*min_percent/100 else Fore.GREEN if current>=max*max_percent/100 else Fore.YELLOW }{current}{Style.RESET_ALL}/{Fore.YELLOW}{max}{Style.RESET_ALL}]"
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
        start_sleep = random.randint(3,12)
        print(f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW} [{session_name}] {Style.RESET_ALL} | Random sleep {start_sleep} second.")
        await asyncio.sleep(start_sleep)
        while True:
            try:
                async with aiohttp.ClientSession(headers=self.headers) as session:
                    tg_handler = TelegramHandler(self.client, session_name, self.platform)
                    tg_web_data, query_id = await tg_handler.get_tg_web_data()

                    auth_data = await self.login(query_id, session)
                    if not auth_data:
                        logger.error(f"Authorization error for {session_name}")
                        break
                    mined = int(auth_data["mined"])
                    dailyReward = auth_data['user']['dailyReward']
                    totalCoins = int(auth_data["user"]["totalCoins"])
                    currentCoins = int(auth_data["user"]["currentCoins"])
                    currentEnergy = int(auth_data["user"]["currentEnergy"])
                    minePerHour = int(auth_data["user"]["minePerHour"])
                    uid = auth_data["user"]['uid']
                    maxEnergy = int(auth_data["user"]["maxEnergy"])
                    coinsPerTap = int(auth_data["user"]["coinsPerTap"])
                    energyPerSec = int(auth_data["user"]["energyPerSec"])

                    sleep_time = int(maxEnergy / energyPerSec)
                    print(f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.GREEN} [{session_name}] {Style.RESET_ALL} | Balance: {Fore.GREEN}{currentCoins}{Style.RESET_ALL} (Mined +{Fore.GREEN}{mined}{Style.RESET_ALL}) | Energy: {self.gen_energy_line(currentEnergy,maxEnergy,25,75)}")
                    while True:
                        # Sync the game data
                        sync_data = await self.sync_gdata(session, currentEnergy, 0)
                        if not sync_data:
                            logger.error(f"Sync error for {session_name}")
                            print(f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.RED} [{session_name}] {Style.RESET_ALL} | Sync error after tapping. Restart session...")
                            break

                        try:
                            currentEnergy = int(sync_data["currentEnergy"])
                        except:
                            logger.error(f"Sync error after tapping for {session_name} restart session...")
                            print(f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.RED} [{session_name}] {Style.RESET_ALL} | Sync error after tapping. Restart session...")
                            break

                        taps = int(round(currentEnergy / coinsPerTap))
                        new_energy = int(max(0, currentEnergy - taps * coinsPerTap))

                        # Perform taps and update energy
                        sync_data = await self.sync_gdata(session, new_energy, taps)
                        if not sync_data:
                            logger.error(f"Sync error after tapping for {session_name}")
                            print(f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.RED} [{session_name}] {Style.RESET_ALL} | Sync error after tapping. Restart session...")
                            break
                        gained_coins = taps * coinsPerTap
                        print(f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.GREEN} [{session_name}] {Style.RESET_ALL} | Success qlyuk! | Energy: {self.gen_energy_line(new_energy,maxEnergy,25,75)} | Balance: {Fore.GREEN}{sync_data['currentCoins']}{Style.RESET_ALL} (+{Fore.GREEN}{gained_coins}{Style.RESET_ALL}) | Sleep {Fore.CYAN}{sleep_time}{Style.RESET_ALL}")
                        await asyncio.sleep(sleep_time)

            except Exception as e:
                logger.exception(f"Error during farming process for {session_name}: {e}")
                break
        return