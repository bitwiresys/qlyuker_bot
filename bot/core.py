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
            "android": "Mozilla/5.0 (Linux; Android 15; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.7049.100 Mobile Safari/537.36 Telegram-Android/11.5.3 (Oneplus DE2117; Android 15; SDK 35; AVERAGE)"
        }

        headers = {
            "Accept": "*/*",
            "Accept-Language": "ru,ru-RU;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
            "content-type": "application/json",
            "Host": "api.qlyuker.io",
            "Klyuk": "0110101101101100011011110110111101101011",
            "Locale": "ru",
            "Onboarding": "2",
            "Origin": "https://qlyuker.io",
            "Referer": "https://qlyuker.io/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "TGPlatform": platform,
            "User-Agent": ua[platform],
        }

        if platform == "android":
            headers["sec-ch-ua"] = '"Android WebView";v="135", "Not-A.Brand";v="8", "Chromium";v="135"'
            headers["sec-ch-ua-mobile"] = "?1"
            headers["sec-ch-ua-platform"] = '"Android"'
            headers["X-Requested-With"] = "com.radolyn.ayugram"

        return headers

    async def sort_upgrades(self, upgrades, friendsCount):
        g_upgraded = []  # List to store suitable upgrades

        # Extract upgrade list from the upgrades object
        upgrade_list = upgrades.get('list', [])

        # Dictionary to store current upgrade levels by their id
        current_levels = {upgrade['id']: upgrade['level'] for upgrade in upgrade_list}

        # Also add levels from user upgrades if they exist
        user_upgrades = upgrades.get('user', {})
        for upgrade_id, upgrade_data in user_upgrades.items():
            if 'level' in upgrade_data:
                current_levels[upgrade_id] = upgrade_data['level']

        for upgrade in upgrade_list:
            # Skip upgrades that have reached max level (indicated by the presence of 'maxLevel')
            if 'maxLevel' in upgrade:
                continue

            # Skip upgrades that have reached levelsCount if present
            if 'levelsCount' in upgrade and upgrade['level'] >= upgrade['levelsCount']:
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
            else:
                # Skip upgrades without next level data
                continue

            # If all conditions are met, add to the g_upgraded list
            g_upgraded.append(upgrade)

        # Sort the g_upgraded list by the ratio of profit increment to price (efficiency)
        g_upgraded.sort(key=lambda x: (x['next']['increment'] / x['next']['price']) if x['next']['price'] > 0 else 0,
                        reverse=True)
        return g_upgraded

    async def login(self, query_id, session):
        """Handles login to the service using Telegram web data."""
        try:
            res = await make_request(session, "POST", "https://api.qlyuker.io/auth/start", {"startData": query_id},
                                     "auth/start", self.headers)
            data = await res.json()

            if "game" not in data:
                logger.error(f"Failed to find game data in the response: {data}")
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
                "https://api.qlyuker.io/game/sync",
                {"clientTime": int(time.time()), "currentEnergy": current_energy, "taps": taps},
                session,
            )
            if not gdata:
                logger.error(f"Sync error for {self.client.name}")
                print(
                    f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.RED} [{self.client.name}] {Style.RESET_ALL} | Sync error after tapping.")
                return None
            return gdata
        except Exception as e:
            logger.exception(f"Error syncing game data: {e}")
            return None

    # async def sync_claim_daily(self, session):
    #     """Claims daily rewards."""
    #     try:
    #         daily = await self.sync("https://qlyuker.io/api/tasks/daily", None, session)
    #         if not daily:
    #             logger.error(f"Sync error for {self.client.name}")
    #             print(f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.RED} [{self.client.name}] {Style.RESET_ALL} | Sync error for claim daily.")
    #             return None
    #         return daily
    #     except Exception as e:
    #         logger.exception(f"Error claiming daily rewards: {e}")
    #         return None

    async def sync_upgrade(self, session, upgrade_id):
        """Attempts to buy an upgrade."""
        try:
            upgrade = await self.sync(
                "https://api.qlyuker.io/upgrades/buy",
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
        start_sleep = random.choice(range(12, 120))
        #print(f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{session_name}]{Style.RESET_ALL} | Random sleep {start_sleep} second.")
        #await asyncio.sleep(start_sleep)

        while True:
            try:
                async with aiohttp.ClientSession(headers=self.headers) as session:
                    tg_handler = TelegramHandler(self.client, session_name, self.platform)
                    _, query_id = await tg_handler.get_tg_web_data()

                    auth_data = await self.login(query_id, session)
                    if auth_data is None:
                        continue

                    # Extract data from the new API structure
                    mined = int(auth_data["app"]["mined"])
                    upgrades = auth_data['upgrades']
                    friendsCount = auth_data['friends']['friendsCount']
                    totalCoins = int(auth_data["game"]["totalCoins"])
                    currentCoins = int(auth_data["game"]["currentCoins"])
                    currentEnergy = int(auth_data["game"]["currentEnergy"])
                    minePerHour = int(auth_data["game"]["minePerHour"])
                    uid = auth_data["user"]['uid']
                    maxEnergy = int(auth_data["game"]["maxEnergy"])
                    coinsPerTap = int(auth_data["game"]["coinsPerTap"])
                    energyPerSec = int(auth_data["game"]["energyPerSec"])

                    # Sort upgrades for auto-upgrading
                    g_upgrades = await self.sort_upgrades(upgrades, friendsCount)

                    print(
                        f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.GREEN}[{session_name}]{Style.RESET_ALL} | "
                        f"Balance: {Fore.GREEN}{currentCoins}{Style.RESET_ALL} "
                        f"(Mined +{Fore.GREEN}{mined}{Style.RESET_ALL}) | "
                        f"Energy: {self.gen_energy_line(currentEnergy, maxEnergy, 25, 75)}")

                    # Calculate taps based on energy and coins per tap
                    if currentEnergy > MIN_SAVE_ENERGY:
                        tap_count = TAP_COUNT
                        if RANDOM_TAP_COUNT:
                            tap_range = RANDOM_TAP_COUNT.split("-")
                            tap_count = random.randint(int(tap_range[0]), int(tap_range[1]))

                        if tap_count > 0:
                            # Limit taps to available energy
                            taps = min(tap_count, int(currentEnergy / coinsPerTap))
                            new_energy = max(0, currentEnergy - taps * coinsPerTap)

                            # Perform taps with sleep between them if configured
                            if SLEEP_PER_TAP > 0 or RANDOM_SLEEP_PER_TAP:
                                for i in range(taps):
                                    sleep_time = SLEEP_PER_TAP
                                    if RANDOM_SLEEP_PER_TAP:
                                        sleep_range = RANDOM_SLEEP_PER_TAP.split("-")
                                        sleep_time = random.uniform(float(sleep_range[0]), float(sleep_range[1]))

                                    # Single tap
                                    single_tap_resp = await self.sync_gdata(session, currentEnergy - coinsPerTap, 1)
                                    if single_tap_resp is None:
                                        break
                                    currentEnergy -= coinsPerTap
                                    await asyncio.sleep(sleep_time)

                                # Final sync after all taps
                                sync_data = await self.sync_gdata(session, new_energy, 0)
                            else:
                                # Bulk taps
                                sync_data = await self.sync_gdata(session, new_energy, taps)

                            if sync_data is not None:
                                gained_coins = taps * coinsPerTap
                                currentCoins = sync_data['currentCoins']
                                print(
                                    f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.GREEN}[{session_name}]{Style.RESET_ALL} | "
                                    f"Successful qlyuk! | Energy: {self.gen_energy_line(new_energy, maxEnergy, 25, 75)} | "
                                    f"Balance: {Fore.GREEN}{currentCoins}{Style.RESET_ALL} (+{Fore.GREEN}{gained_coins}{Style.RESET_ALL})")

                    # Handle auto-upgrades if enabled
                    if USE_AUTO_UPGRADES:
                        await asyncio.sleep(random.randint(8, 34))

                        for u in g_upgrades:
                            if u['id'] == 'coinsPerTap':
                                continue

                            if u['id'] == 'restoreEnergy':
                                if 'upgradedAt' not in u or time.time() - u['upgradedAt'] >= 3600:
                                    # Only proceed with restoreEnergy if it's been more than an hour since last upgrade
                                    pass
                                else:
                                    continue

                            # Check if we can afford the upgrade
                            if 'next' in u:
                                next_price = u['next']['price']
                                if next_price > currentCoins or MIN_SAVE_BALANCE >= currentCoins - next_price:
                                    continue

                            # Try to buy the upgrade
                            r_updates = await self.sync_upgrade(session, u['id'])
                            if r_updates is None:
                                continue

                            if isinstance(r_updates, str) and "Слишком рано для улучшения" in r_updates:
                                continue

                            # Update variables from response
                            currentCoins = r_updates['currentCoins']
                            upgrade_mine_diff = r_updates['minePerHour'] - minePerHour

                            print(
                                f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.GREEN}[{session_name}]{Style.RESET_ALL} | "
                                f"Successful update! | Mining: {Fore.GREEN}{minePerHour}{Style.RESET_ALL} "
                                f"(+{Fore.GREEN}{upgrade_mine_diff}{Style.RESET_ALL}) | "
                                f"Balance: {Fore.GREEN}{currentCoins}{Style.RESET_ALL}")

                            # Update variables for next iteration
                            minePerHour = r_updates['minePerHour']
                            maxEnergy = r_updates['maxEnergy']
                            currentEnergy = r_updates['currentEnergy']

                            # Sleep a bit between upgrades
                            await asyncio.sleep(random.choice(range(1, 3)))

                    # Calculate sleep time before next loop
                    sleep_time = min(10800, int(maxEnergy / energyPerSec) if energyPerSec > 0 else 10800)  # 3 hours max

                    print(
                        f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.GREEN}[{session_name}]{Style.RESET_ALL} | "
                        f"Sleep {Fore.CYAN}{sleep_time}{Style.RESET_ALL} seconds")

                    # Sleep before next cycle
                    await asyncio.sleep(sleep_time)

            except Exception as e:
                logger.exception(f"Error during farming process for {session_name}: {e}")
                break

        return


