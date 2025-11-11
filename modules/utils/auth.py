from telethon import TelegramClient
from config import API_ID, API_HASH, SESSION_NAME

def get_client():
    return TelegramClient(SESSION_NAME, API_ID, API_HASH)

async def connect_client():
    client = get_client()
    await client.start()
    print("[+] Connected to Telegram API")
    return client
