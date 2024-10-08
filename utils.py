import asyncio
import aiohttp
import configparser
from loguru import logger

def load_config(config_file=".conf"):
    """Loads configuration from the specified .conf file."""
    config = configparser.ConfigParser()
    config.read(config_file)
    return config

def insert_after(d, key, new_key, new_value):
    """Helper function to insert new key-value pair after a specific key."""
    items = list(d.items())
    index = items.index((key, d[key]))
    items.insert(index + 1, (new_key, new_value))
    return dict(items)

async def handle_error(error: Exception, response_text: str, context: str):
    """Handles errors during requests."""
    logger.error(f"Unknown error while {context}: <lr>{error}</lr> | Response text: {response_text}...")
    await asyncio.sleep(3)

async def make_request(http_client: aiohttp.ClientSession, method: str, url: str, json_data: dict, error_context: str, headers: dict = None):
    """Makes an HTTP request and handles errors."""
    response_text = ""
    try:
        response = await http_client.request(
            method=method, url=url, json=json_data, ssl=False, headers=headers
        )
        return response
    except Exception as error:
        await handle_error(error, response_text, error_context)
        return {}

