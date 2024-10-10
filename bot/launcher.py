import os
import time
import asyncio
import glob
import threading
import random
from bot.utils import load_config, load_version
from colorama import init, Fore, Style
from loguru import logger
from pyrogram import Client
from bot.core import FarmBot

# Initialize colorama for colored console output
init()

# Load version from the .ver file
ver = load_version()

# Load configurations from the .conf file
config = load_config()

# Extract version
VER = ver.get("version", "v")

# Extract log settings from the configuration
LOG_FILE = config.get("settings", "log_file")
LOG_ROTATION = config.get("settings", "log_rotation")
LOG_RETENTION = config.get("settings", "log_retention")
LOG_LEVEL = config.get("settings", "log_level")

# Configure the logger
logger.add(LOG_FILE, rotation=LOG_ROTATION, retention=LOG_RETENTION, level=LOG_LEVEL)

# Banner to display at the start
BANNER = f"""{Style.DIM}{Fore.MAGENTA}
    █████   ██▓   ▓██   ██▓ █    ██  ██ ▄█▀▓█████  ██▀███   ▄▄▄▄    ▒█████  ▄▄▄█████▓
  ▒██▓  ██▒▓██▒    ▒██  ██▒ ██  ▓██▒ ██▄█▒ ▓█   ▀ ▓██ ▒ ██▒▓█████▄ ▒██▒  ██▒▓  ██▒ ▓▒
  ▒██▒  ██░▒██░     ▒██ ██░▓██  ▒██░▓███▄░ ▒███   ▓██ ░▄█ ▒▒██▒ ▄██▒██░  ██▒▒ ▓██░ ▒░
  ░██  █▀ ░▒██░     ░ ▐██▓░▓▓█  ░██░▓██ █▄ ▒▓█  ▄ ▒██▀▀█▄  ▒██░█▀  ▒██   ██░░ ▓██▓ ░ 
  ░▒███▒█▄ ░██████▒ ░ ██▒▓░▒▒█████▓ ▒██▒ █▄░▒████▒░██▓ ▒██▒░▓█  ▀█▓░ ████▓▒░  ▒██▒ ░ 
  ░░ ▒▒░ ▒ ░ ▒░▓  ░  ██▒▒▒ ░▒▓▒ ▒ ▒ ▒ ▒▒ ▓▒░░ ▒░ ░░ ▒▓ ░▒▓░░▒▓███▀▒░ ▒░▒░▒░   ▒ ░░   
   ░ ▒░  ░ ░ ░ ▒  ░▓██ ░▒░ ░░▒░ ░ ░ ░ ░▒ ▒░ ░ ░  ░  ░▒ ░ ▒░▒░▒   ░   ░ ▒ ▒░     ░    
     ░   ░   ░ ░   ▒ ▒ ░░   ░░░ ░ ░ ░ ░░ ░    ░     ░░   ░  ░    ░ ░ ░ ░ ▒    ░      
      ░        ░  ░░ ░        ░     ░  ░      ░  ░   ░      ░          ░ ░           
                   ░ ░                                           ░                   
"""


def dun_title():
    while True:
        for x in ["\\", "∣", "/", "–"]:
            time.sleep(0.2)
            os.system(f"title qlyuker_bot {x} v{VER} {x} github.com/bitwiresys/qlyuker_bot")
def display_banner():
    """Display the banner with a small delay for each line for effect."""
    threading.Thread(target=dun_title, args=()).start()
    for line in BANNER.split("\n"):
        print(Style.DIM + Fore.MAGENTA + line + Style.RESET_ALL)
        time.sleep(0.2)
    print(
        f"    {Style.DIM}{Fore.BLUE}Made by bitwiresys for public use. "
        f"If you purchase this, you have been scammed.{Style.RESET_ALL}\n"
    )
    time.sleep(0.2)


def get_session_names():
    """Return a list of session names from the 'sessions/' directory."""
    return [
        os.path.splitext(os.path.basename(file))[0]
        for file in glob.glob("sessions/*.session")
    ]


async def start_farm_process(session_name):
    """Initialize the Telegram client and start the farming process."""
    api_id = config.getint("telegram", "api_id")
    api_hash = config.get("telegram", "api_hash")

    # Initialize the Telegram client with the session
    client = Client(session_name, api_id=api_id, api_hash=api_hash,workdir="sessions/")
    farm_bot = FarmBot(client,random.choice(["ios", "android"]))

    # Start the farming process
    await farm_bot.farming()


async def launch_process():
    """Main entry point for launching the farming process for all sessions."""
    # Display the banner at the start
    display_banner()

    # Get all session names from the 'sessions/' folder
    session_names = get_session_names()

    if not session_names:
        logger.error("No sessions found!")
        print(f"{Fore.RED}No sessions found!{Style.RESET_ALL}")
        return

    print(f" → [{time.strftime('%Y-%m-%d %H:%M:%S')}] {Fore.GREEN}Starting farm process for {len(session_names)} sessions...{Style.RESET_ALL}")

    # Run the farming process for all available sessions asynchronously
    await asyncio.gather(*[start_farm_process(session_name) for session_name in session_names])