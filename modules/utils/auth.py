from telethon import TelegramClient
from config import API_ID, API_HASH, SESSION_NAME
from modules.utils.output import info, error

def get_client():
    """Create and return a Telegram client instance."""
    return TelegramClient(SESSION_NAME, API_ID, API_HASH)

async def connect_client():
    """Connect to Telegram API and return client instance."""
    client = get_client()
    try:
        await client.start()
        info("Connected to Telegram API")
        return client
    except Exception as e:
        error(f"Failed to connect to Telegram API: {e}")
        raise
