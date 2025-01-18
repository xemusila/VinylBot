import asyncpg
import logging
from config import DB_CONFIG


logging.basicConfig(level=logging.INFO)
async def get_db_connection():
    try:
        return await asyncpg.connect(**DB_CONFIG)
    except Exception as e:
        logging.error(f"Ошибка подключения к базе данных: {e}")
        raise
