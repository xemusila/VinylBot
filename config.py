import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("botToken")
GigaChatKey = os.getenv("GigaChatKey")
DB_CONFIG = {
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
}
