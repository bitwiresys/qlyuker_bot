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
USE_MAX_ENERGY_TAPS = config.getboolean("bot", "use_max_energy_taps") if config.get("bot", "use_max_energy_taps") != '' else False
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

    async def sort_upgrades(self, upgrades, friendsCount, shared_config):
        print(
            f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{self.client.name}]{Style.RESET_ALL} | Starting sort_upgrades with {len(upgrades.get('list', []))} upgrades and {friendsCount} friends")
        g_upgraded = []  # List to store suitable upgrades
        current_time = int(time.time())

        # Extract upgrade list from the upgrades object
        upgrade_list = upgrades.get('list', [])
        if not upgrade_list:
            print(
                f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{self.client.name}]{Style.RESET_ALL} | No upgrades found in the list")

        # Dictionary to store current upgrade levels by their id
        current_levels = {upgrade['id']: upgrade['level'] for upgrade in upgrade_list}

        # Also add levels from user upgrades if they exist
        user_upgrades = upgrades.get('user', {})
        for upgrade_id, upgrade_data in user_upgrades.items():
            if 'level' in upgrade_data:
                current_levels[upgrade_id] = upgrade_data['level']

        # Получаем настройки задержек из shared_config
        day_limitation_delay = shared_config.get('dayLimitationUpgradeDelay', 3600)  # По умолчанию 1 час
        upgrade_delays = shared_config.get('upgradeDelay', {})

        for upgrade in upgrade_list:
            # Проверка кулдауна на основе upgradedAt
            if 'upgradedAt' in upgrade:
                last_upgrade_time = upgrade['upgradedAt']

                # Определяем задержку для конкретного апгрейда
                cooldown_period = day_limitation_delay  # По умолчанию

                # Проверяем есть ли дневное ограничение
                if 'dayLimitation' in upgrade and upgrade['dayLimitation'] > 0:
                    cooldown_period = day_limitation_delay
                else:
                    # Используем задержку в зависимости от уровня апгрейда
                    upgrade_level = str(upgrade.get('level', 1))
                    if upgrade_level in upgrade_delays:
                        cooldown_period = upgrade_delays[upgrade_level]
                    elif upgrade['id'] == 'restoreEnergy':
                        cooldown_period = 3600  # 1 час для восстановления энергии

                # Проверяем прошло ли достаточно времени
                time_since_upgrade = current_time - last_upgrade_time
                if time_since_upgrade < cooldown_period:
                    remaining_minutes = int((cooldown_period - time_since_upgrade) / 60)
                    print(
                        f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{self.client.name}]{Style.RESET_ALL} | Upgrade {upgrade['id']} on cooldown. {remaining_minutes} minutes remaining.")
                    continue

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
        print(
            f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.GREEN}[{self.client.name}]{Style.RESET_ALL} | Found {len(g_upgraded)} suitable upgrades, sorted by efficiency")

        if g_upgraded:
            top_upgrades = [f"{u['id']}(+{u['next']['increment']}/{u['next']['price']})" for u in g_upgraded[:3]]
            print(
                f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.GREEN}[{self.client.name}]{Style.RESET_ALL} | Top upgrades: {', '.join(top_upgrades)}")

        return g_upgraded

    async def login(self, query_id, session):
        """Handles login to the service using Telegram web data."""
        try:
            print(
                f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{self.client.name}]{Style.RESET_ALL} | Attempting login with query_id: {query_id[:15]}...")
            res = await make_request(session, "POST", "https://api.qlyuker.io/auth/start", {"startData": query_id},
                                     "auth/start", self.headers)

            status_code = res.status
            print(
                f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{self.client.name}]{Style.RESET_ALL} | Login response status code: {status_code}")

            if status_code != 200:
                print(
                    f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.RED}[{self.client.name}]{Style.RESET_ALL} | Login failed with status code {status_code}")
                return None

            data = await res.json()

            if "game" not in data:
                print(
                    f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.RED}[{self.client.name}]{Style.RESET_ALL} | Failed to find game data in the response")
                return None

            print(
                f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.GREEN}[{self.client.name}]{Style.RESET_ALL} | Login successful for user: {data['user']['uid']}")
            return data
        except Exception as error:
            print(
                f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.RED}[{self.client.name}]{Style.RESET_ALL} | Exception during login: {str(error)}")
            await handle_error(error, "", "getting Access Token")
            return None

    async def sync(self, url, payload, session):
        """Sends a sync request to the specified URL."""
        try:
            print(
                f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{self.client.name}]{Style.RESET_ALL} | Sending sync request to {url}")

            async with session.post(url, json=payload, headers=self.headers) as res:
                status_code = res.status
                print(
                    f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{self.client.name}]{Style.RESET_ALL} | Sync response status code: {status_code}")

                if status_code != 200:
                    print(
                        f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.RED}[{self.client.name}]{Style.RESET_ALL} | Sync request failed with status code {status_code}")
                    return None

                response_text = await res.text()

                if is_json(response_text):
                    response_json = await res.json()
                    return response_json

                print(
                    f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{self.client.name}]{Style.RESET_ALL} | Received non-JSON response")
                return response_text
        except Exception as e:
            print(
                f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.RED}[{self.client.name}]{Style.RESET_ALL} | Exception during sync request to {url}: {str(e)}")
            return None

    async def sync_gdata(self, session, current_energy, taps):
        """Synchronizes game data."""
        try:
            print(
                f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{self.client.name}]{Style.RESET_ALL} | Syncing game data with energy: {current_energy}, taps: {taps}")

            gdata = await self.sync(
                "https://api.qlyuker.io/game/sync",
                {"clientTime": int(time.time()), "currentEnergy": current_energy, "taps": taps},
                session,
            )

            if not gdata:
                print(
                    f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.RED}[{self.client.name}]{Style.RESET_ALL} | Sync error: No response data received")
                return None

            if 'currentCoins' not in gdata:
                print(
                    f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.RED}[{self.client.name}]{Style.RESET_ALL} | Sync error: Invalid response format")
                return None

            print(
                f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.GREEN}[{self.client.name}]{Style.RESET_ALL} | Game data sync successful. Current coins: {gdata['currentCoins']}, Energy: {gdata['currentEnergy']}")
            return gdata
        except Exception as e:
            print(
                f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.RED}[{self.client.name}]{Style.RESET_ALL} | Error syncing game data: {str(e)}")
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
    async def process_tasks(self, session, tasks):
        """Automatically complete available tasks."""
        print(
            f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{self.client.name}]{Style.RESET_ALL} | Processing {len(tasks)} tasks")

        for task in tasks:
            if task.get('completed', False):
                continue

            task_id = task['id']
            task_kind = task['kind']
            reward = task.get('meta', {}).get('reward', 0)

            print(
                f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{self.client.name}]{Style.RESET_ALL} | Processing task: {task_id} ({task_kind}) - Reward: {reward}")

            # Проверяем задания с проверкой времени
            if 'time' in task and 'checkDelay' in task.get('meta', {}):
                current_time = int(time.time())
                check_delay = task['meta']['checkDelay']
                time_since_action = current_time - task['time']

                if time_since_action >= check_delay:
                    # Можно проверить выполнение задания
                    result = await self.sync(
                        "https://api.qlyuker.io/tasks/check",
                        {"taskId": task_id},
                        session
                    )
                    if result:
                        print(
                            f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.GREEN}[{self.client.name}]{Style.RESET_ALL} | Task {task_id} completed! Reward: +{reward}")

            await asyncio.sleep(random.randint(2, 5))

    async def claim_task_reward(self, session, task_id):
        """Claim reward for completed task."""
        try:
            result = await self.sync(
                "https://api.qlyuker.io/tasks/claim",
                {"taskId": task_id},
                session
            )
            return result
        except Exception as e:
            print(
                f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.RED}[{self.client.name}]{Style.RESET_ALL} | Error claiming task reward: {e}")
            return None
    async def sync_upgrade(self, session, upgrade_id):
        """Attempts to buy an upgrade."""
        try:
            print(
                f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{self.client.name}]{Style.RESET_ALL} | Attempting to buy upgrade: {upgrade_id}")

            upgrade = await self.sync(
                "https://api.qlyuker.io/upgrades/buy",
                {"upgradeId": upgrade_id},
                session,
            )

            if not upgrade:
                print(
                    f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.RED}[{self.client.name}]{Style.RESET_ALL} | Upgrade sync error: No response data received")
                return None

            if isinstance(upgrade, str):
                print(
                    f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{self.client.name}]{Style.RESET_ALL} | Upgrade response is a string: {upgrade}")
                return upgrade

            if 'currentCoins' not in upgrade:
                print(
                    f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.RED}[{self.client.name}]{Style.RESET_ALL} | Upgrade sync error: Invalid response format")
                return None

            print(
                f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.GREEN}[{self.client.name}]{Style.RESET_ALL} | Upgrade {upgrade_id} purchased successfully. New balance: {upgrade['currentCoins']}")
            return upgrade
        except Exception as e:
            print(
                f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.RED}[{self.client.name}]{Style.RESET_ALL} | Error buying upgrade: {str(e)}")
            return None


    async def farming(self):
        """Main farming loop with enhanced functionality."""
        session_name = self.client.name
        start_sleep = random.choice(range(12, 120))
        print(
            f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{session_name}]{Style.RESET_ALL} | Starting enhanced farming with random sleep {start_sleep} seconds")
        await asyncio.sleep(start_sleep)

        while True:
            try:
                async with aiohttp.ClientSession(headers=self.headers) as session:
                    print(
                        f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{session_name}]{Style.RESET_ALL} | Initializing Telegram handler")
                    tg_handler = TelegramHandler(self.client, session_name, self.platform)

                    print(
                        f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{session_name}]{Style.RESET_ALL} | Getting Telegram web data")
                    _, query_id = await tg_handler.get_tg_web_data()

                    print(
                        f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{session_name}]{Style.RESET_ALL} | Attempting login")
                    auth_data = await self.login(query_id, session)
                    if auth_data is None:
                        print(
                            f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.RED}[{session_name}]{Style.RESET_ALL} | Login failed, retrying next cycle")
                        await asyncio.sleep(60)
                        continue

                    # Extract data from the new API structure
                    print(
                        f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{session_name}]{Style.RESET_ALL} | Extracting data from API response")
                    mined = int(auth_data["app"]["mined"])
                    upgrades = auth_data['upgrades']
                    shared_config = auth_data.get('sharedConfig', {})
                    friendsCount = auth_data['friends'].get('friendsCountWithYandexID', 0)
                    totalCoins = int(auth_data["game"]["totalCoins"])
                    currentCoins = int(auth_data["game"]["currentCoins"])
                    currentEnergy = int(auth_data["game"]["currentEnergy"])
                    currentTickets = int(auth_data["game"]["currentTickets"])
                    minePerHour = int(auth_data["game"]["minePerHour"])
                    uid = auth_data["user"]['uid']
                    maxEnergy = int(auth_data["game"]["maxEnergy"])
                    coinsPerTap = int(auth_data["game"]["coinsPerTap"])
                    energyPerSec = int(auth_data["game"]["energyPerSec"])

                    # New data sections
                    tasks = auth_data.get('tasks', [])
                    shop_items = auth_data.get('shop', [])
                    tournaments = auth_data.get('tournaments', [])
                    team_info = auth_data.get('team', {})
                    leaderboard = auth_data.get('leaderboard', [])

                    print(f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.GREEN}[{session_name}]{Style.RESET_ALL} | "
                          f"Balance: {Fore.GREEN}{currentCoins}{Style.RESET_ALL} "
                          f"(Mined +{Fore.GREEN}{mined}{Style.RESET_ALL}) | "
                          f"Energy: {self.gen_energy_line(currentEnergy, maxEnergy, 25, 75)} | "
                          f"Tickets: {Fore.YELLOW}{currentTickets}{Style.RESET_ALL}")

                    # Process tasks automatically
                    if tasks:
                        print(
                            f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{session_name}]{Style.RESET_ALL} | Processing {len(tasks)} available tasks")
                        await self.process_tasks(session, tasks)

                    # Sort upgrades for auto-upgrading
                    print(
                        f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{session_name}]{Style.RESET_ALL} | Sorting upgrades")
                    g_upgrades = await self.sort_upgrades(upgrades, friendsCount, shared_config)

                    # Calculate taps based on energy and coins per tap
                    print(
                        f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{session_name}]{Style.RESET_ALL} | Checking if tapping is needed (energy: {currentEnergy}, min save: {MIN_SAVE_ENERGY})")
                    if currentEnergy > MIN_SAVE_ENERGY:
                        tap_count = TAP_COUNT

                        # Если включена опция максимального использования энергии
                        if USE_MAX_ENERGY_TAPS:
                            # Используем всю доступную энергию, учитывая минимальный запас
                            tap_count = int((currentEnergy - MIN_SAVE_ENERGY) / coinsPerTap)
                            print(
                                f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{session_name}]{Style.RESET_ALL} | Using maximum energy taps: {tap_count}")
                        elif RANDOM_TAP_COUNT:
                            try:
                                tap_range = RANDOM_TAP_COUNT.split("-")
                                tap_count = random.randint(int(tap_range[0]), int(tap_range[1]))
                                print(
                                    f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{session_name}]{Style.RESET_ALL} | Random tap count selected: {tap_count} from range {RANDOM_TAP_COUNT}")
                            except Exception as e:
                                print(
                                    f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.RED}[{session_name}]{Style.RESET_ALL} | Error parsing random_tap_count: {e}")
                                print(
                                    f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{session_name}]{Style.RESET_ALL} | Using default tap count: {tap_count}")

                        print(
                            f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{session_name}]{Style.RESET_ALL} | Final tap count: {tap_count}")

                        if tap_count > 0:
                            # Limit taps to available energy
                            taps = min(tap_count, int(currentEnergy / coinsPerTap))
                            new_energy = max(0, currentEnergy - taps * coinsPerTap)
                            print(
                                f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{session_name}]{Style.RESET_ALL} | Will perform {taps} taps, energy will drop from {currentEnergy} to {new_energy}")

                            # Всегда используем массовые тапы для максимальной эффективности
                            print(
                                f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{session_name}]{Style.RESET_ALL} | Using bulk taps (count: {taps})")
                            sync_data = await self.sync_gdata(session, new_energy, taps)

                            if sync_data is not None:
                                gained_coins = taps * coinsPerTap
                                currentCoins = sync_data['currentCoins']
                                print(
                                    f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.GREEN}[{session_name}]{Style.RESET_ALL} | "
                                    f"Successful qlyuk! | Energy: {self.gen_energy_line(new_energy, maxEnergy, 25, 75)} | "
                                    f"Balance: {Fore.GREEN}{currentCoins}{Style.RESET_ALL} (+{Fore.GREEN}{gained_coins}{Style.RESET_ALL})")
                            else:
                                print(
                                    f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.RED}[{session_name}]{Style.RESET_ALL} | Tapping failed, no valid response data")
                        else:
                            print(
                                f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{session_name}]{Style.RESET_ALL} | No taps to perform (tap_count = {tap_count})")
                    else:
                        print(
                            f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{session_name}]{Style.RESET_ALL} | Not enough energy for taps: {currentEnergy} <= {MIN_SAVE_ENERGY}")

                    # Handle auto-upgrades if enabled
                    if USE_AUTO_UPGRADES:
                        print(
                            f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{session_name}]{Style.RESET_ALL} | Auto-upgrades enabled, processing {len(g_upgrades)} available upgrades")
                        upgrade_delay = random.randint(8, 34)
                        print(
                            f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{session_name}]{Style.RESET_ALL} | Waiting {upgrade_delay} seconds before upgrades")
                        await asyncio.sleep(upgrade_delay)

                        upgrade_count = 0
                        for u in g_upgrades:
                            if u['id'] == 'coinsPerTap':
                                print(
                                    f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{session_name}]{Style.RESET_ALL} | Skipping coinsPerTap upgrade")
                                continue

                            if u['id'] == 'restoreEnergy':
                                if 'upgradedAt' not in u or time.time() - u['upgradedAt'] >= 3600:
                                    print(
                                        f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{session_name}]{Style.RESET_ALL} | restoreEnergy upgrade available (last upgrade > 1 hour)")
                                    pass
                                else:
                                    print(
                                        f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{session_name}]{Style.RESET_ALL} | Skipping restoreEnergy upgrade (too soon)")
                                    continue

                            # Check if we can afford the upgrade
                            if 'next' in u:
                                next_price = u['next']['price']
                                if next_price > currentCoins:
                                    print(
                                        f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{session_name}]{Style.RESET_ALL} | Cannot afford upgrade {u['id']} - price: {next_price}, balance: {currentCoins}")
                                    continue
                                if MIN_SAVE_BALANCE >= currentCoins - next_price:
                                    print(
                                        f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{session_name}]{Style.RESET_ALL} | Not enough balance after upgrade {u['id']} - remain: {currentCoins - next_price}, min save: {MIN_SAVE_BALANCE}")
                                    continue
                                print(
                                    f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{session_name}]{Style.RESET_ALL} | Attempting to buy upgrade {u['id']} for {next_price} coins")
                            else:
                                print(
                                    f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{session_name}]{Style.RESET_ALL} | Upgrade {u['id']} has no next level data")
                                continue

                            # Try to buy the upgrade
                            r_updates = await self.sync_upgrade(session, u['id'])
                            if r_updates is None:
                                print(
                                    f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.RED}[{session_name}]{Style.RESET_ALL} | Failed to buy upgrade {u['id']}")
                                continue

                            if isinstance(r_updates, str) and "Слишком рано для улучшения" in r_updates:
                                print(
                                    f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{session_name}]{Style.RESET_ALL} | Too early for upgrade {u['id']}: {r_updates}")
                                continue

                            # Update variables from response
                            try:
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
                                upgrade_count += 1
                            except KeyError as e:
                                print(
                                    f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.RED}[{session_name}]{Style.RESET_ALL} | Missing key in upgrade response: {e}")
                                continue

                            # Sleep a bit between upgrades
                            await asyncio.sleep(random.choice(range(1, 3)))

                        print(
                            f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.GREEN}[{session_name}]{Style.RESET_ALL} | Completed upgrades: {upgrade_count} out of {len(g_upgrades)} available")
                    else:
                        print(
                            f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.YELLOW}[{session_name}]{Style.RESET_ALL} | Auto-upgrades disabled")

                    # Calculate sleep time before next loop
                    sleep_time = min(10800, int(maxEnergy / energyPerSec) if energyPerSec > 0 else 10800)  # 3 hours max
                    print(f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.GREEN}[{session_name}]{Style.RESET_ALL} | "
                          f"Sleep {Fore.CYAN}{sleep_time}{Style.RESET_ALL} seconds")

                    # Sleep before next cycle
                    await asyncio.sleep(sleep_time)

            except Exception as e:
                print(f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] | {Fore.RED}[{session_name}]{Style.RESET_ALL} | "
                      f"Error during farming process: {str(e)}")
                # Wait before retrying
                await asyncio.sleep(300)

        return