import logging
from aiogram.types import Update, Message, CallbackQuery
import json
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from utils.database import get_db_connection


class UserActionLoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Update, data: dict):

        user_id = event.from_user.id
        action_details = {}


        if isinstance(event, CallbackQuery):
            action_type = "callback"
            action_details = {
                "callback_data": event.data
            }
        elif event.sticker: 
            action_type = "sticker"
            action_details = {
                "sticker_file_id": event.sticker.file_id
            }
        elif event.text.startswith("/"):
            action_type = "command"
            action_details = {
                "command": event.text
            }  
        elif isinstance(event, Message):
            action_type = "message"
            action_details = {
                "text": event.text
            }
        
        

        try:
            action_details_json = json.dumps(action_details)
            conn = await get_db_connection()

            await conn.execute(
                """
                INSERT INTO userActions (userID, actionType, actionDetails)
                VALUES ($1, $2, $3)
                """,
                user_id,
                action_type,
                action_details_json
            )
            await conn.close() 
        except Exception as e:
            logging.error(f"Ошибка записи в базу данных: {e}")

        return await handler(event, data)
