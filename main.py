import asyncio
from bot.launcher import launch_process

if __name__ == "__main__":
    # Run the main launch process asynchronously
    asyncio.run(launch_process())