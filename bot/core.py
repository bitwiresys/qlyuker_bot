import random
import time
import aiohttp
import asyncio
from bot.utils import make_request, handle_error, insert_after, load_config, is_json
from bot.telegram_handler import TelegramHandler
from loguru import logger
from colorama import Fore, Style

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

class FarmBot:
    def __init__(self, client, platform):
        self.client = client
        self.platform = platform
        self.headers = self.gen_headers(self.platform)

    def gen_energy_line(self,current,max,min_percent,max_percent):
        return f"[{Fore.RED if current<=max*min_percent/100 else Fore.GREEN if current>=max*max_percent/100 else Fore.YELLOW }{current}{Style.RESET_ALL}/{Fore.GREEN}{max}{Style.RESET_ALL}]"
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

    async def sort_upgrades(self, upgrades, friendsCount):
        g_upgraded = []  # List to store suitable upgrades

        # Dictionary to store current upgrade levels by their id
        current_levels = {upgrade['id']: upgrade['level'] for upgrade in upgrades}

        for upgrade in upgrades:
            # Skip upgrades that have reached max level (indicated by the presence of 'maxLevel')
            if 'maxLevel' in upgrade:
                continue

            # Check conditions for upgrades
            if 'condition' in upgrade:
                condition = upgrade['condition']

                # Condition for friends
                if condition['kind'] == 'friends':
                    if friendsCount < condition['friends']:
                        continue  # Do not add if not enough friends

                # Condition for other upgrades
                elif condition['kind'] == 'upgrade':
                    required_upgrade_id = condition['upgradeId']
                    required_level = condition['level']
                    if required_upgrade_id in current_levels:
                        if current_levels[required_upgrade_id] < required_level:
                            continue  # Do not add if required upgrade level is insufficient

            # Check the level of the upgrade only if MAX_UPGRADE_LVL > 0
            if MAX_UPGRADE_LVL > 0 and upgrade['level'] >= MAX_UPGRADE_LVL:
                continue  # Do not add if level exceeds the maximum allowed

            # Check next upgrade price only if MAX_UPGRADE_COST > 0
            if 'next' in upgrade:
                next_price = upgrade['next'].get('price', float('inf'))
                next_increment = upgrade['next'].get('increment', 0)

                if MAX_UPGRADE_COST > 0 and next_price > MAX_UPGRADE_COST:
                    continue  # Do not add if next upgrade price exceeds the maximum allowed

                # Check profit increment only if MIN_UPGRADE_PROFIT > 0
                if MIN_UPGRADE_PROFIT > 0 and next_increment < MIN_UPGRADE_PROFIT:
                    continue  # Do not add if profit increment is below the minimum allowed

            # If all conditions are met, add to the g_upgraded list
            g_upgraded.append(upgrade)

        # Sort the g_upgraded list by the ratio of profit increment to price (efficiency)
        g_upgraded.sort(key=lambda x: (x['next']['increment'] / x['next']['price']) if x['next']['price'] > 0 else 0,reverse=True)
        return g_upgraded
    async def login(self, query_id, session):
        """Handles login to the service using Telegram web data."""
        try:
            res = await make_request(session, "POST", "https://qlyuker.io/api/auth/start", {"startData": query_id}, "api/auth/start", self.headers)
            data = await res.json()

            if "user" not in data:
                logger.error(f"Failed to find user data in the response: {data}")
                return None
            if not data:
                logger.error(f"Authorization error for {self.client.name}")
                return None
            return data
        except Exception as error:
            await handle_error(error, "", "getting Access Token")
            return None

    async def sync(self, url, payload, session):
        """Sends a sync request to the specified URL."""
        try:
            async with session.post(url, json=payload, headers=self.headers) as res:
                if is_json(await res.text()):
                    return await res.json()
                return await res.text()
        except Exception as e:
            logger.exception(f"Sync error: {e}")
            return None

    async def sync_gdata(self, session, current_energy, taps):
        """Synchronizes game data."""
        try:
            gdata = await self.sync(
                "https://qlyuker.io/api/game/sync",
                {"clientTime": int(time.time()), "currentEnergy": current_energy, "taps": taps},
                session,
            )
            if not gdata:
                logger.error(f"Sync error for {self.client.name}")
                print(f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.RED} [{self.client.name}] {Style.RESET_ALL} | Sync error after tapping.")
                return None
            return gdata
        except Exception as e:
            logger.exception(f"Error syncing game data: {e}")
            return None

    async def sync_claim_daily(self, session):
        """Claims daily rewards."""
        try:
            daily = await self.sync("https://qlyuker.io/api/tasks/daily", {}, session)
            if not daily:
                logger.error(f"Sync error for {self.client.name}")
                print(f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.RED} [{self.client.name}] {Style.RESET_ALL} | Sync error for claim daily.")
                return None
            return daily
        except Exception as e:
            logger.exception(f"Error claiming daily rewards: {e}")
            return None

    async def sync_upgrade(self, session, upgrade_id):
        """Attempts to buy an upgrade."""
        try:
            upgrade = await self.sync(
                "https://qlyuker.io/api/upgrades/buy",
                {"upgradeId": upgrade_id},
                session,
            )
            if not upgrade:
                logger.error(f"Sync error for {self.client.name}")
                print(
                    f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.RED} [{self.client.name}] {Style.RESET_ALL} | Sync error for upgrade.")
                return None
            return upgrade
        except Exception as e:
            logger.exception(f"Error buying upgrade: {e}")
            return None

    async def farming(self):
        """Main farming loop."""
        session_name = self.client.name
        start_sleep = random.choice(range(12,120))
        print(f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{session_name}]{Style.RESET_ALL} | Random sleep {start_sleep} second.")
        await asyncio.sleep(start_sleep)
        while True:
            try:
                async with aiohttp.ClientSession(headers=self.headers) as session:
                    tg_handler = TelegramHandler(self.client, session_name, self.platform)
                    tg_web_data, query_id = await tg_handler.get_tg_web_data()

                    auth_data = await self.login(query_id, session)
                    if auth_data == None:
                        continue
                    mined = int(auth_data["mined"])
                    upgrades = auth_data['upgrades']
                    dailyReward = auth_data['user']['dailyReward']
                    friendsCount = auth_data['user']['friendsCount']
                    totalCoins = int(auth_data["user"]["totalCoins"])
                    currentCoins = int(auth_data["user"]["currentCoins"])
                    currentEnergy = int(auth_data["user"]["currentEnergy"])
                    minePerHour = int(auth_data["user"]["minePerHour"])
                    uid = auth_data["user"]['uid']
                    maxEnergy = int(auth_data["user"]["maxEnergy"])
                    coinsPerTap = int(auth_data["user"]["coinsPerTap"])
                    energyPerSec = int(auth_data["user"]["energyPerSec"])
                    g_upgrades = await self.sort_upgrades(upgrades,friendsCount)
                    print(f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.GREEN}[{session_name}]{Style.RESET_ALL} | Balance: {Fore.GREEN}{currentCoins}{Style.RESET_ALL} (Mined +{Fore.GREEN}{mined}{Style.RESET_ALL}) | Energy: {self.gen_energy_line(currentEnergy,maxEnergy,25,75)}")
                    if not dailyReward["claimed"]:
                        claim_daily = await self.sync_claim_daily(session)
                        print(f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.GREEN}[{session_name}]{Style.RESET_ALL} | Claim daily reward! | Day: {claim_daily['dailyReward']['day']} | Reward: +{Fore.GREEN}{claim_daily['reward']}{Style.RESET_ALL}")
                    taps = int(round(currentEnergy / coinsPerTap))
                    new_energy = int(max(0, currentEnergy - taps * coinsPerTap))

                    # Perform taps and update energy
                    sync_data = await self.sync_gdata(session, new_energy, taps)
                    if sync_data == None:
                        continue
                    gained_coins = taps * coinsPerTap
                    sleep_time = int(maxEnergy / energyPerSec)
                    currentCoins = sync_data['currentCoins']
                    print(f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.GREEN}[{session_name}]{Style.RESET_ALL} | Successful qlyuk! | Energy: {self.gen_energy_line(new_energy, maxEnergy, 25, 75)} | Balance: {Fore.GREEN}{currentCoins}{Style.RESET_ALL} (+{Fore.GREEN}{gained_coins}{Style.RESET_ALL}) | Sleep {Fore.CYAN}{sleep_time}{Style.RESET_ALL}")
                    if USE_AUTO_UPGRADES:
                        await asyncio.sleep(random.randint(8, 34))

                        for u in g_upgrades:
                            if u['id'] == 'coinsPerTap':
                                continue
                            if u['id'] == 'restoreEnergy':
                                if 'upgradedAt' not in u or time.time() - u['upgradedAt'] >= 3600:
                                    sleep_time = random.choice(range(1, 3))
                                else:
                                    continue
                            if 'next' in u:
                                if u['next']['price'] > currentCoins and MIN_SAVE_BALANCE >= currentCoins - u['next']['price']:
                                    continue
                            r_updates = await self.sync_upgrade(session, u['id'])
                            if r_updates == None:
                                continue
                            if r_updates == "Слишком рано для улучшения":
                                continue
                            currentCoins = r_updates['currentCoins']
                            print(f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.GREEN}[{session_name}]{Style.RESET_ALL} | Successful update! | Mining: {Fore.GREEN}{minePerHour}{Style.RESET_ALL} (+{Fore.GREEN}{r_updates['minePerHour'] - minePerHour}{Style.RESET_ALL}) | Balance: {Fore.GREEN}{currentCoins}{Style.RESET_ALL}")
                            minePerHour = r_updates['minePerHour']
                            await asyncio.sleep(random.choice(range(1,3)))
                    await session.close()
                    await asyncio.sleep(sleep_time)
                    continue

            except Exception as e:
                logger.exception(f"Error during farming process for {session_name}: {e}")
                break
        return