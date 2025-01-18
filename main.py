import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher, html, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, BotCommand, BotCommandScopeDefault
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import TOKEN, GigaChatKey
from utils.database import get_db_connection
from logging_middleware import UserActionLoggingMiddleware
import asyncpg
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from langchain_gigachat.chat_models.gigachat import GigaChat
from langchain.prompts import PromptTemplate
from langchain.memory import ConversationBufferMemory

logging.basicConfig(level=logging.INFO)


bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
 

texts = {
        "add": "Добавить пластинку",
        "del":"Удалить информацию",
        "search":"Поиск информации",
        "edit":"Редактировать информацию",
        "interests":"Подобрать музыку по интересам",
        "view":"Просмотр коллекции"
    }

kb_list = [
        [KeyboardButton(text=texts["add"])],
        [KeyboardButton(text=texts["del"])],
        [KeyboardButton(text=texts["search"])],
        [KeyboardButton(text=texts["edit"])],
        [KeyboardButton(text=texts["interests"])],
        [KeyboardButton(text=texts["view"])],
      ]

kb_yes_no = [
        [KeyboardButton(text='Да')],
        [KeyboardButton(text='Нет')],
]

kb_got_it = [
        [KeyboardButton(text='Понятно')],
]


class AddVinyl(StatesGroup):
    get_artist_info = State()
    artist_info_confirmation = State()
    waiting_for_artist_info = State()
    get_album_info = State()
    album_info_confirmation = State()
    waiting_for_album_info = State()
    get_label_info = State()
    label_info_confirmation = State()
    waiting_for_label_info = State()
    get_other_info = State()

class InfoActions(StatesGroup):
    delete_which = State()
    delete_show_artist = State()
    delete_artist = State()
    delete_show_album = State()
    delete_album = State()
    delete_show_label = State()
    delete_label = State()
    delete_show_record = State()
    delete_record = State()
    search_which = State()
    search_album = State()
    search_artist = State()
    search_label = State()
    search_record = State()
    edit_which = State()
    edit_show_artist = State()
    edit_artist = State()
    to_start = State()

class RegistrationForm(StatesGroup):
    name = State()
    form = State()

class AITalks(StatesGroup):
    get_message = State()


class RegistrationCheckMiddleware:
    async def __call__(
        self,
        handler: callable,
        event: Message,
        data: dict,
    ) -> None:
        
        state: FSMContext = data.get("state")
        curr_state = await state.get_state()
        
        if curr_state and curr_state == RegistrationForm.name or data['event_update'].message.text == '/register':
            return await handler(event, data)
        user_id = event.from_user.id
        conn = await get_db_connection()
        user = await conn.fetchrow("SELECT userID FROM Users WHERE userID=$1", user_id)
        await conn.close()
        if not user:
            await event.answer("Сначала зарегистрируйтесь! Используйте команду /register.")
            return
        return await handler(event, data)


@dp.message(Command("register"))
async def cmd_register(message: Message, state: FSMContext):
    user_id = message.from_user.id
    conn = await get_db_connection()
    user = await conn.fetchrow("SELECT userID FROM Users WHERE userID=$1", user_id)
    conn.close()
    if user:
        await message.answer("Вы уже зарегистрированы!")
        state.set_state(InfoActions.to_start)
        return
    
    await message.answer("Начнем регистрацию. Как к вам обращаться?")
    await state.set_state(RegistrationForm.name)

@dp.message(RegistrationForm.name)
async def create_name(message: Message, state: FSMContext):
    name = message.text 
    user = message.from_user
    username = user.username
    user_id = user.id

    conn = await get_db_connection()
    await conn.fetchrow(
                        """
                        INSERT INTO Users (userID, username, name, notif)
                        VALUES ($1, $2, $3, False)
                        """,
                        user_id, username, name 
                    )

    await conn.close()
    keyboard = ReplyKeyboardMarkup(
            keyboard=kb_got_it, resize_keyboard=True, one_time_keyboard=True
    )
    await message.answer(f"Отлично, {name}! Регистрация завершена. Можете пользоваться", reply_markup=keyboard)
    await state.set_state(InfoActions.to_start)


async def send_long_message(message: Message, text):
    for i in range(0, len(text), 4096):
        part = text[i:i + 4096]

        await message.answer(part)

async def search_user(conn, id):
    row = await conn.fetch("SELECT name FROM Users WHERE userID=$1", id)
    return row[0]['name']

def search_artist(conn, name):
    return conn.fetchrow("SELECT artistID FROM Artist WHERE artistName=$1", name)

def search_album(conn, album, artist):
    return conn.fetchrow(
                         """
                         SELECT al.albumID
                         FROM Album al
                         JOIN Artist ar ON al.artistID=ar.artistID
                         WHERE al.albumName = $1 AND ar.artistName=$2
                         """,
                         album, artist
                        )

def search_label(conn, name):
    return conn.fetchrow("SELECT labelID FROM Label WHERE labelName=$1", name)

def search_record(conn, album, label, size, cond, year, user):
    return conn.fetchrow(
        """
        SELECT r.recordID
        FROM Record r
        JOIN Album al on r.albumID=al.albumID
        JOIN Label l on r.labelID=l.labelID
        WHERE r.recordSize = $1 AND r.recordCond = $2
        AND r.recordYear = $3 AND al.albumName = $4 AND l.labelName = $5
        AND userID = $6
        """,
        size, cond, year, album, label, user
    )


async def info_artist(conn, message, name):
    rows = await conn.fetch(
        """
        SELECT 
            artistName, artistCountry
        FROM Artist WHERE artistName = $1
        """, 
        name
    )
    response = "\n".join(
        [
            f"Название исполнителя: {row['artistname']}\n"
            f"Страна исполнителя: {row['artistcountry']}"
            for row in rows
        ]
    )
    await message.answer(f"Текущая информация об исполнителе:\n{response}")

async def info_album(conn, message, album, artist):
    rows = await conn.fetch(
        """
        SELECT 
            al.albumName, al.albumYear, al.genre, ar.artistName
        FROM Album al
        JOIN Artist ar ON al.artistID = ar.artistID
        WHERE albumName = $1 AND artistName = $2
        """, 
        album, artist
    )
    response = "\n".join(
        [
            f"Название альбома: {row['albumname']}\n"
            f"Год: {row['albumyear']}\n"
            f"Жанр: {row['genre']}\n"
            f"Исполнитель: {row['artistname']}\n"
            for row in rows
        ]
    )
    await message.answer(f"Текущая информация об альбоме:\n{response}")

async def info_label(conn, message, name):
    rows = await conn.fetch(
        """
        SELECT 
            labelName, labelCountry
        FROM Label WHERE labelName = $1
        """, 
        name
    )
    response = "\n".join(
        [
            f"Название компании звукозаписи: {row['labelname']}\n"
            f"Страна: {row['labelcountry']}"
            for row in rows
        ]
    )
    await message.answer(f"Текущая информация о лейбле:\n{response}")

@dp.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    conn = await get_db_connection()
    name = await search_user(conn, user_id)
    await conn.close()

    commands = [  
                  BotCommand(command='start', description='Сначала'),
                  BotCommand(command='help', description='Помощь'),
                  BotCommand(command='register', description='Регистрация'),
                  BotCommand(command='on', description='Вкл уведомления'),
                  BotCommand(command='off', description='Выкл уведомления'),
                ]
    await bot.set_my_commands(commands, BotCommandScopeDefault())

    texts = {
        "info": "Что ты умеешь?",
        "start": "Начинаем!"
    }


    kb_list = [
        [KeyboardButton(text=texts["info"])],
        [KeyboardButton(text=texts["start"])],
      ]
    keyboard = ReplyKeyboardMarkup(keyboard=kb_list, resize_keyboard=True, one_time_keyboard=True)
    await message.answer(f"Привет, {html.bold(name)}!")
    await message.answer('Приступим?', reply_markup=keyboard)
    


@dp.message((F.text.lower().strip().strip() == 'что ты умеешь?'))
@dp.message(Command('help'))
async def info(message: Message, state: FSMContext):
    kb_list = [
        [KeyboardButton(text="Поехали!")],
      ]
    keyboard = ReplyKeyboardMarkup(keyboard=kb_list, resize_keyboard=True, one_time_keyboard=True)
    await message.answer(
        "Я такой же любитель винила, как и вы!\nБуду помогать организовывать вашу коллекцию пластинок. "
        "Я умею хранить информацию о пластинках: об исполнителе, альбоме, годе выпуска, жанре, лейбле, "
        "размере самой пластинки и её состоянии. "
        "Также помогу найти все пластинки, определённого альбома, которые есть у вас "
        "в коллекции. Или все альбомы с определённым названием. "
        'Например, выведу все альбомы с названием "Master of Puppets" (хотя вряд ли их будет много). '
        "Можете добавлять новые записи, редактировать и удалять старые в любой момент. Я с радостью помогу."
        "\nВот команды, которыми вы можете пользоваться при общении со мной:\n\n"
        "/start - начать общение сначала\n"
        "/help - что я умею\n"
        "/register - зарегистрироваться (можно только один раз)\n"
        "/on - включить напоминания послушать музыку\n"
        "/off - выключать напоминания послушать музыку\n"
        "\nЧуть не забыл! Ещё я могу находить альбомы и исполнителей по твоим интересам. "
        "В этом мне помогает GigaChat.\nНу что, приступим?", 
        reply_markup=keyboard
    )
    

@dp.message(InfoActions.to_start)
@dp.message((F.text.lower().strip().strip()=="начинаем!") | (F.text.lower().strip().strip()=="поехали!"))
async def get_started(message: Message, state:FSMContext):
    keyboard = ReplyKeyboardMarkup(keyboard=kb_list, resize_keyboard=True, one_time_keyboard=True)
    await message.answer("Нажимайте кнопку",reply_markup=keyboard)
    await state.clear()


"""
    Добавление информации
"""

@dp.message(F.text.lower().strip().strip() == "добавить пластинку")
async def add_record_handler(message: Message, state: FSMContext):
    await message.answer(
        "Начнём вводить информацию о пластинке.\n"
        "Для начала введите название исполнителя:"
    )
    await state.set_state(AddVinyl.get_artist_info)

@dp.message(AddVinyl.get_artist_info)
async def get_or_create_artist(message: types.Message, state: FSMContext):
    artist_name = message.text.lower().strip().strip()
    conn = await get_db_connection()
    artist = await search_artist(conn, artist_name)
    if artist:
        await state.update_data(artist_id=artist["artistid"])
        await message.answer("Теперь введите название альбома:")
        await state.set_state(AddVinyl.get_album_info)
        await conn.close()
    else:
        # Сохраняем имя исполнителя в состояние
        await state.update_data(artist_name=artist_name)

        # Отправляем запрос пользователю
        keyboard = ReplyKeyboardMarkup(
            keyboard=kb_yes_no, resize_keyboard=True, one_time_keyboard=True
        )
        await message.answer(
            "Похоже, я не знаю такого исполнителя. Хотите заполнить дополнительную информацию о нём?",
            reply_markup=keyboard,
        )

        await state.set_state(AddVinyl.artist_info_confirmation)

@dp.message(AddVinyl.artist_info_confirmation, F.text.lower().strip().strip() == "да")
async def confirm_artist_creation(message: types.Message, state: FSMContext):
    await message.answer("Введите информацию об исполнителе в формате: Страна")
    await state.set_state(AddVinyl.waiting_for_artist_info)

@dp.message(AddVinyl.artist_info_confirmation, F.text.lower().strip().strip() == "нет")
async def no_artist_info(message: types.Message, state: FSMContext):
    data = await state.get_data()
    artist_name = data.get("artist_name")
    conn = await get_db_connection()
    artist = await conn.fetchrow(
            """
            INSERT INTO Artist (artistName)
            VALUES ($1)
            RETURNING artistID
            """,
            artist_name, 
        )

        # Сохраняем artistID в состояние
    await state.update_data(artist_id=artist["artistid"])
    await conn.close()

    await message.answer("Хорошо, я добавил в базу только название исполнителя.")
    await message.answer("Теперь введите название альбома:")
    await state.set_state(AddVinyl.get_album_info)

@dp.message(AddVinyl.waiting_for_artist_info)
async def create_artist_handler(message: types.Message, state: FSMContext):
    try:

        data = await state.get_data()
        artist_name = data.get("artist_name")
        artist_country = message.text.lower().strip()

        conn = await get_db_connection()

        artist = await conn.fetchrow(
            """
            INSERT INTO Artist (artistName, artistCountry)
            VALUES ($1, $2)
            RETURNING artistID
            """,
            artist_name, artist_country,
        )

        await state.update_data(artist_id=artist["artistid"])
        await conn.close()

        await message.answer(f"Исполнитель '{artist_name}' успешно добавлен!")
        await message.answer("Теперь введите название альбома:")
        await state.set_state(AddVinyl.get_album_info)

    except asyncpg.UniqueViolationError as e:
        await message.answer("Ошибка! Исполнитель с такими характеристиками уже существует в коллекции.")
        logging.error(f"Ошибка добавления исполнителя: {e}")

    except Exception as e:
        await message.answer("Ошибка при добавлении исполнителя. Попробуйте снова.")
        logging.error(f"Ошибка добавления исполнителя: {e}")

    
@dp.message(AddVinyl.get_album_info)
async def get_or_create_album(message: types.Message, state: FSMContext):
    album_name = message.text.lower().strip().strip()
    data = await state.get_data()
    artist_id = data.get("artist_id")
    conn = await get_db_connection()
    artist = await conn.fetchrow("SELECT artistName FROM Artist WHERE artistID=$1", artist_id)
    artist_name = artist["artistname"]
    album = await search_album(conn, album_name, artist_name)
    if album:
        await state.update_data(album_id=album["albumid"])
        await message.answer("Теперь введите название звукозаписывающей компании:")
        await state.set_state(AddVinyl.get_label_info)
        await conn.close()
    else:
        await state.update_data(album_name=album_name)

        keyboard = ReplyKeyboardMarkup(
            keyboard=kb_yes_no, resize_keyboard=True, one_time_keyboard=True
        )
        await message.answer(
            "Похоже, я не знаю такого альбома. Хотите заполнить дополнительную информацию о нём?",
            reply_markup=keyboard,
        )

        await state.set_state(AddVinyl.album_info_confirmation)

@dp.message(AddVinyl.album_info_confirmation, F.text.lower().strip() == "да")
async def confirm_album_creation(message: types.Message, state: FSMContext):
    await message.answer("Введите информацию об альбоме в формате: Год выпуска альбома, Название жанра")
    await state.set_state(AddVinyl.waiting_for_album_info)

@dp.message(AddVinyl.album_info_confirmation, F.text.lower().strip() == "нет")
async def no_album_info(message: types.Message, state: FSMContext):
    data = await state.get_data()
    artist_id = data.get("artist_id")
    album_name = data.get("album_name")
    conn = await get_db_connection()
    album = await conn.fetchrow(
            """
            INSERT INTO Album (albumName, artistID)
            VALUES ($1, $2)
            RETURNING albumID
            """,
            album_name, artist_id
        )

    await state.update_data(album_id=album["albumid"])
    await conn.close()
    
    await message.answer("Хорошо, я добавил в базу только название альбома.")
    await message.answer("Теперь введите название звукозаписывающей компании:")
    await state.set_state(AddVinyl.get_label_info)

@dp.message(AddVinyl.waiting_for_album_info)
async def create_album_handler(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        album_name = data.get("album_name")
        artist_id = data.get("artist_id")
        add_data = message.text.split(', ')
        album_year = int(add_data[0])
        genre = add_data[1]

        conn = await get_db_connection()

        album = await conn.fetchrow(
            """
            INSERT INTO Album (albumName, albumYear, genre, artistID)
            VALUES ($1, $2, $3, $4)
            RETURNING albumID
            """,
            album_name, album_year, genre, artist_id
        )

        await state.update_data(album_id=album["albumid"])
        await conn.close()

        await message.answer(f"Альбом '{album_name}' успешно добавлен!")
        await message.answer("Теперь введите название звукозаписывающей компании:")
        await state.set_state(AddVinyl.get_label_info)

    except asyncpg.UniqueViolationError as e:
        await message.answer("Ошибка! Альбом с такими характеристиками уже существует в коллекции.")
        logging.error(f"Ошибка добавления альбома: {e}")

    except Exception as e:
        await message.answer("Ошибка при добавлении альбома. Проверьте формат и попробуйте снова.")
        logging.error(f"Ошибка добавления альбома: {e}")

@dp.message(AddVinyl.get_label_info)
async def get_or_create_label(message: types.Message, state: FSMContext):
    label_name = message.text.lower().strip()
    conn = await get_db_connection()
    label = await search_label(conn, label_name)
    if label:
        await state.update_data(label_id=label["labelid"])
        await message.answer("Введите остальные данные в формате: СОСТОЯНИЕ ПЛАСТИНКИ, размер, год выпуска:")
        await state.set_state(AddVinyl.get_other_info)
        await conn.close()
    else:
        await state.update_data(label_name=label_name)

        # Отправляем запрос пользователю
        keyboard = ReplyKeyboardMarkup(
            keyboard=kb_yes_no, resize_keyboard=True, one_time_keyboard=True
        )
        await message.answer(
            "Похоже, я не знаю такой компании. Хотите заполнить дополнительную информацию о ней?",
            reply_markup=keyboard,
        )

        # Переходим в состояние подтверждения
        await state.set_state(AddVinyl.label_info_confirmation)

@dp.message(AddVinyl.label_info_confirmation, F.text.lower().strip() == "да")
async def confirm_label_creation(message: types.Message, state: FSMContext):
    await message.answer("Введите информацию о компании в формате: Страна")
    await state.set_state(AddVinyl.waiting_for_label_info)

@dp.message(AddVinyl.label_info_confirmation, F.text.lower().strip() == "нет")
async def no_label_info(message: types.Message, state: FSMContext):
    data = await state.get_data()
    label_name = data.get("label_name")
    conn = await get_db_connection()
    album = await conn.fetchrow(
            """
            INSERT INTO Label (labelName)
            VALUES ($1)
            RETURNING labelID
            """,
            label_name
        )

    await state.update_data(label_id=album["labelid"])
    await conn.close()
    
    await message.answer("Хорошо, я добавил в базу только название звукозаписывающей компании.")
    await message.answer("Введите остальные данные в формате: СОСТОЯНИЕ ПЛАСТИНКИ, размер, год выпуска:")
    await state.set_state(AddVinyl.get_other_info)

@dp.message(AddVinyl.waiting_for_label_info)
async def create_label_handler(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        label_name = data.get("label_name")
        label_country = message.text.lower().strip()

        conn = await get_db_connection()

        label = await conn.fetchrow(
            """
            INSERT INTO Label (labelName, labelCountry)
            VALUES ($1, $2)
            RETURNING labelID
            """,
            label_name, label_country
        )

        await state.update_data(label_id=label["labelid"])
        await conn.close()

        # Сообщаем пользователю об успехе
        await message.answer(f"Компания '{label_name}' успешно добавлена!")
        await message.answer("Введите остальные данные в формате: СОСТОЯНИЕ ПЛАСТИНКИ, размер, год выпуска:")
        await state.set_state(AddVinyl.get_other_info)

    except asyncpg.UniqueViolationError as e:
        await message.answer("Ошибка! Компания с такими характеристиками уже существует в коллекции.")
        logging.error(f"Ошибка добавления компании: {e}")

    except Exception as e:
        await message.answer("Ошибка при добавлении компании звукозаписи. Попробуйте снова.")
        logging.error(f"Ошибка добавления компании: {e}")

@dp.message(AddVinyl.get_other_info)
async def add_record(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        user_id = message.from_user.id
        album_id = data.get("album_id")
        label_id = data.get("label_id")

        new_data = message.text.split(', ')
        cond = new_data[0]
        size = new_data[1]
        year = int(new_data[2])

        conn = await get_db_connection()

        record = await conn.fetchrow(
            """
            INSERT INTO Record (recordSize, recordCond, recordYear, albumID, labelID, userID)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING recordID
            """,
            size, cond, year, album_id, label_id, user_id
        )

        await state.update_data(record_id=record["recordid"])
        await conn.close()

        # Сообщаем пользователю об успехе
        keyboard = ReplyKeyboardMarkup(
            keyboard=kb_got_it, resize_keyboard=True, one_time_keyboard=True
        )
        await message.answer(f"Новая пластинка успешно добавлена!", reply_markup=keyboard)
        await state.set_state(InfoActions.to_start)
    except asyncpg.UniqueViolationError as e:
        await message.answer("Ошибка! Пластинка с такими характеристиками уже существует в коллекции.")
        logging.error(f"Ошибка добавления пластинки: {e}")
    except (asyncpg.exceptions.DataError, ValueError, asyncpg.exceptions.CheckViolationError) as e:
        await message.answer("Ошибка! Проверьте формат данных. Пример: NEW, LP, 1986")
        await message.answer("Подсказка: состояние пластинки может быть одним из следующих:"
                             "'NEW', 'M', 'NM', 'VG+', 'VG', 'G+', 'G', 'P', 'B'")
        await message.answer("Подсказка: размер пластинки может быть одним из следующих:"
                             "'LP', '12-inch single', '7-inch', '10-inch', 'EP', 'other'")
        logging.error(f"Ошибка добавления пластинки: {e}")
    except Exception as e:
        await message.answer("Произошла неожиданная ошибка. Проверьте формат и попробуйте снова.")
        logging.error(f"Неожиданная ошибка: {e}")

"""
    Удаление записей
"""

@dp.message(F.text.lower().strip() == "удалить информацию")
async def edit_info_handler(message: Message, state: FSMContext):
    texts_objects = {
        "artist": "Исполнитель",
        "album": "Альбом",
        "label": "Звукозаписывающая компания",
        "record": "Пластинка"
    }

    builder_objects = InlineKeyboardBuilder()
    builder_objects.button(text=texts_objects["artist"], callback_data="artist")
    builder_objects.button(text=texts_objects["album"], callback_data="album")
    builder_objects.button(text=texts_objects["label"], callback_data="label")
    builder_objects.button(text=texts_objects["record"], callback_data="record")
    builder_objects.adjust(1)
    await message.answer(
        "Что будем удалять?", reply_markup=builder_objects.as_markup()
    )
    await state.set_state(InfoActions.delete_which)

"""
    Удаление исполнителя
"""

@dp.message(InfoActions.delete_which, F.text.lower().strip() == "исполнитель")
@dp.callback_query(F.data == 'artist')
async def which_artist(message: Message, state: FSMContext):
    await message.answer(
        "Какого исполнителя хотите удалить?"
    )
    await state.set_state(InfoActions.delete_show_artist)

@dp.message(InfoActions.delete_show_artist)
async def show_artist(message: Message, state: FSMContext):
    try:
        conn = await get_db_connection()
        artist_name = message.text
        artist = await search_artist(conn, artist_name)
        if artist:
            await info_artist(conn, message, artist_name)
            await conn.close()
            keyboard = ReplyKeyboardMarkup(
            keyboard=kb_yes_no, resize_keyboard=True, one_time_keyboard=True
            )
            await message.reply("Уверены, что хотите удалить исполнителя?", reply_markup=keyboard)
            await state.update_data(artist_id = artist['artistid'])
            await state.set_state(InfoActions.delete_artist)
        else:
            keyboard = ReplyKeyboardMarkup(
            keyboard=kb_got_it, resize_keyboard=True, one_time_keyboard=True
            )
            await message.answer("Такого исполнителя нет в базе!", reply_markup=keyboard)
            await state.set_state(InfoActions.to_start)
    except Exception as e:
        await message.answer("Ошибка при получении данных из базы. Проверьте формат и повторите попытку")
        logging.error(f"Ошибка получении информации об исполнителе: {e}")

@dp.message(InfoActions.delete_artist)
async def delete_artist(message: Message, state: FSMContext):
    try:
        text = message.text.lower().strip()
        if text == 'да':
            st_data = await state.get_data()
            artist_id = st_data.get("artist_id")
            conn = await get_db_connection()
            await conn.fetchrow(
                """
                DELETE from Artist
                WHERE artistID = $1
                """,
                artist_id
            )
            await message.answer("Исполнитель успешно удалён")
    except asyncpg.exceptions.ForeignKeyViolationError as e:
        await message.answer("Нельзя удалить исполнителя, пока на него ссылается альбом. Сначала удалите альбом")
        logging.error(f"Ошибка удаления исполнителя: {e}")
    except Exception as e:
        await message.answer("Ошибка при удалении исполнителя. Попробуйте снова.")
        logging.error(f"Ошибка удаления исполнителя: {e}")
    finally:
        await state.set_state(InfoActions.to_start)
        keyboard = ReplyKeyboardMarkup(
            keyboard=kb_got_it, resize_keyboard=True, one_time_keyboard=True
        )
        await message.answer("Возврат к началу", reply_markup=keyboard)

"""
    Удаление альбома
"""

@dp.message(InfoActions.delete_which, F.text.lower().strip() == "альбом")
@dp.callback_query(F.data == 'album')
async def which_album(message: Message, state: FSMContext):
    await message.answer(
        "Какой альбом хотите удалить? Напишите информацию в формате: название альбома, исполнитель"
    )
    await state.set_state(InfoActions.delete_show_album)

@dp.message(InfoActions.delete_show_album)
async def show_album(message: Message, state: FSMContext):
    try:
        conn = await get_db_connection()
        data = message.text.split(', ')
        album_name = data[0].lower().strip()
        artist = data[1].lower().strip()
        album = await search_album(conn, album_name, artist)
        if album:
            await info_album(conn, message, album_name, artist)
            await conn.close()
            keyboard = ReplyKeyboardMarkup(
            keyboard=kb_yes_no, resize_keyboard=True, one_time_keyboard=True
            )
            await message.reply("Уверены, что хотите удалить альбом?", reply_markup=keyboard)
            await state.update_data(album_id = album['albumid'])
            await state.set_state(InfoActions.delete_album)
        else:
            keyboard = ReplyKeyboardMarkup(
            keyboard=kb_got_it, resize_keyboard=True, one_time_keyboard=True
            )
            await message.answer("Такого альбома нет в базе!", reply_markup=keyboard)
            await state.set_state(InfoActions.to_start)
    except Exception as e:
        await message.answer("Ошибка при получении данных из базы. Проверьте формат и повторите попытку")
        logging.error(f"Ошибка получении информации об альбоме: {e}")

@dp.message(InfoActions.delete_album)
async def delete_album(message: Message, state: FSMContext):
    try:
        text = message.text.lower().strip()
        if text == 'да':
            st_data = await state.get_data()
            album_id = st_data.get("album_id")
            conn = await get_db_connection()
            await conn.fetchrow(
                """
                DELETE from Album
                WHERE albumID = $1
                """,
                album_id
            )
            await message.answer("Альбом успешно удалён")
    except asyncpg.exceptions.ForeignKeyViolationError as e:
        await message.answer("Нельзя удалить альбом, пока на него ссылается пластинка. Сначала удалите запись о пластинке")
        logging.error(f"Ошибка удаления альбома: {e}")
    except Exception as e:
        await message.answer("Ошибка при удалении альбома. Попробуйте снова.")
        logging.error(f"Ошибка удаления альбома: {e}")
    finally:
        await state.set_state(InfoActions.to_start)
        keyboard = ReplyKeyboardMarkup(
            keyboard=kb_got_it, resize_keyboard=True, one_time_keyboard=True
        )
        await message.answer("Возврат к началу", reply_markup=keyboard)

"""
    Удаление лейбла
"""

@dp.message(InfoActions.delete_which, F.text.lower().strip() == "звукозаписывающая компания")
@dp.callback_query(F.data == 'label')
async def which_label(message: Message, state: FSMContext):
    await message.answer(
        "Какую компанию хотите удалить?"
    )
    await state.set_state(InfoActions.delete_show_label)

@dp.message(InfoActions.delete_show_label)
async def show_label(message: Message, state: FSMContext):
    try:
        conn = await get_db_connection()
        name = message.text.lower().strip()
        label = await search_label(conn, name)
        if label:
            await info_label(conn, message, name)
            await conn.close()
            keyboard = ReplyKeyboardMarkup(
            keyboard=kb_yes_no, resize_keyboard=True, one_time_keyboard=True
            )
            await message.reply("Уверены, что хотите удалить запись?", reply_markup=keyboard)
            await state.update_data(label_id = label['labelid'])
            await state.set_state(InfoActions.delete_label)
        else:
            keyboard = ReplyKeyboardMarkup(
            keyboard=kb_got_it, resize_keyboard=True, one_time_keyboard=True
            )
            await message.answer("Такой компании нет в базе!", reply_markup=keyboard)
            await state.set_state(InfoActions.to_start)
    except Exception as e:
        await message.answer("Ошибка при получении данных из базы.")
        logging.error(f"Ошибка получении информации о лейбле: {e}")

@dp.message(InfoActions.delete_label)
async def delete_label(message: Message, state: FSMContext):
    try:
        text = message.text.lower().strip()
        if text == 'да':
            st_data = await state.get_data()
            label_id = st_data.get("label_id")
            conn = await get_db_connection()
            await conn.fetchrow(
                """
                DELETE from Label
                WHERE labelID = $1
                """,
                label_id
            )
            await message.answer("Компания успешно удалена")
    except asyncpg.exceptions.ForeignKeyViolationError as e:
        await message.answer("Нельзя удалить компанию, пока на неё ссылается пластинка. Сначала удалите запись о пластинке")
        logging.error(f"Ошибка удаления лейбла: {e}")
    except Exception as e:
        await message.answer("Ошибка при удалении компании. Попробуйте снова.")
        logging.error(f"Ошибка удаления лейбла: {e}")
    finally:
        await state.set_state(InfoActions.to_start)
        keyboard = ReplyKeyboardMarkup(
            keyboard=kb_got_it, resize_keyboard=True, one_time_keyboard=True
        )
        await message.answer("Возврат к началу", reply_markup=keyboard)

"""
    Удаление пластинки
"""

@dp.message(InfoActions.delete_which, F.text.lower().strip() == "пластинка")
@dp.callback_query(F.data == 'record')
async def which_record(message: Message, state: FSMContext):
    await message.answer(
        "Какую пластинку хотите удалить? Напишите все её характеристики в формате: "
        "Название Альбома, Звукозаписывающая Компания, Размер, Состояние, Год"
    )
    await state.set_state(InfoActions.delete_show_record)

@dp.message(InfoActions.delete_show_record)
async def show_record(message: Message, state: FSMContext):
    try:
        conn = await get_db_connection()
        data = message.text.split(", ")
        album, label, size, cond, year = (data[i] for i in range(5))
        album, label = album.lower().strip(), label.lower().strip()
        user_id = message.from_user.id
        record = await search_record(conn, album, label, size, cond, int(year), user_id)
        await conn.close()
        if record:
            keyboard = ReplyKeyboardMarkup(
            keyboard=kb_yes_no, resize_keyboard=True, one_time_keyboard=True
            )
            await message.reply("Уверены, что хотите удалить запись?", reply_markup=keyboard)
            await state.update_data(record_id = record['recordid'])
            await state.set_state(InfoActions.delete_record)
        else:
            keyboard = ReplyKeyboardMarkup(
            keyboard=kb_got_it, resize_keyboard=True, one_time_keyboard=True
            )
            await message.answer("Такой пластинки нет в базе!", reply_markup=keyboard)
            await state.set_state(InfoActions.to_start)
    except Exception as e:
        await message.answer("Ошибка при получении данных из базы. Проверьте формат записи и попробуйте снова")
        logging.error(f"Ошибка получении информации о пластинке: {e}")

@dp.message(InfoActions.delete_record)
async def delete_record(message: Message, state: FSMContext):
    try:
        text = message.text.lower().strip()
        if text == 'да':
            st_data = await state.get_data()
            record_id = st_data.get("record_id")
            conn = await get_db_connection()
            await conn.fetchrow(
                """
                DELETE from Record
                WHERE recordID = $1
                """,
                record_id
            )
            await message.answer("Пластинка успешно удалена")
    except Exception as e:
        await message.answer("Ошибка при удалении пластинки. Попробуйте снова.")
        logging.error(f"Ошибка удаления пластинки: {e}")
    finally:
        await state.set_state(InfoActions.to_start)
        keyboard = ReplyKeyboardMarkup(
            keyboard=kb_got_it, resize_keyboard=True, one_time_keyboard=True
        )
        await message.answer("Возврат к началу", reply_markup=keyboard)

"""
    Поиск информации
"""

@dp.message(F.text.lower().strip() == "поиск информации")
async def search_which(message: Message, state: FSMContext):
    texts = {
        "record": "Пластинку по альбому",
        "album": "Альбом по названию",
        "artist": "Исполнителя по названию",
        "label": "Лейбл по названию"
    }

    kb_list = [
        [KeyboardButton(text=texts["record"])],
        [KeyboardButton(text=texts["album"])],
        [KeyboardButton(text=texts["artist"])],
        [KeyboardButton(text=texts["label"])],
      ]
    keyboard = ReplyKeyboardMarkup(keyboard=kb_list, resize_keyboard=True, one_time_keyboard=True)
    await message.answer("Что хотите найти?", reply_markup=keyboard)
    await state.set_state(InfoActions.search_which)

"""
    Поиск пластинок
"""

@dp.message(InfoActions.search_which, F.text.lower().strip() == 'пластинку по альбому')
async def search_record_by_album(message: Message, state: FSMContext):
    await message.answer("Хорошо, давайте найдём пластинки по альбому. Напишите название альбома")
    await state.set_state(InfoActions.search_record)

@dp.message(InfoActions.search_record)
async def get_record(message: Message, state: FSMContext):
    try:
        user_id = message.from_user.id
        album = message.text.lower().strip()
        conn = await get_db_connection()
        rows = await conn.fetch(
                """
                SELECT 
                    a.albumName, ar.artistName, l.labelName,
                    r.recordCond, r.recordSize, r.recordYear
                FROM Record r
                JOIN Album a ON r.albumID = a.albumID
                JOIN Artist ar ON a.artistID = ar.artistID
                JOIN Label l ON r.labelID = l.labelID
                WHERE a.albumName = $1 AND r.userID = $2
                """, album, user_id
        )
        await conn.close()

        if rows:
            response = "\n\n".join(
                [
                    f"Исполнитель: {row['artistname']}\n"
                    f"Альбом: {row['albumname']}\n"
                    f"Год: {row['recordyear']}\n"
                    f"Состояние: {row['recordcond']}\n"
                    f"Размер: {row['recordsize']}\n"
                    f"Лейбл: {row['labelname']}"
                    for row in rows
                ]
            )
            await message.answer(f"Пластинки с этим альбомом:\n\n")
            await send_long_message(message, response)
        else:
            await message.answer("Нет пластинок с этим альбомом")

    except Exception as e:
        await message.answer("Ошибка при получении данных из базы.")
        logging.error(f"Ошибка поиска пластинки: {e}")
    finally:
        await state.set_state(InfoActions.to_start)
        keyboard = ReplyKeyboardMarkup(
            keyboard=kb_got_it, resize_keyboard=True, one_time_keyboard=True
        )
        await message.answer("Возврат к началу", reply_markup=keyboard)

"""
    Поиск альбомов
"""

@dp.message(InfoActions.search_which, F.text.lower().strip() == 'альбом по названию')
async def search_album_by_name(message: Message, state: FSMContext):
    await message.answer("Хорошо, давайте найдём альбом по названию. Напишите название альбома")
    await state.set_state(InfoActions.search_album)

@dp.message(InfoActions.search_album)
async def get_album(message: Message, state: FSMContext):
    try:
        album = message.text.lower().strip()
        conn = await get_db_connection()
        rows = await conn.fetch(
                """
                SELECT 
                    a.albumName, ar.artistName, albumYear, genre
                FROM Album a 
                JOIN Artist ar ON a.artistID = ar.artistID
                WHERE a.albumName = $1
                """, album
        )
        await conn.close()

        if rows:
            response = "\n\n".join(
                [
                    f"Исполнитель: {row['artistname']}\n"
                    f"Альбом: {row['albumname']}\n"
                    f"Год: {row['albumyear']}\n"
                    f"Жанр: {row['genre']}\n"
                    for row in rows
                ]
            )
            await message.answer(f"Альбомы с этим названием:\n\n")
            await send_long_message(message, response)
        else:
            await message.answer("Нет альбомов с таким названием")

    except Exception as e:
        await message.answer("Ошибка при получении данных из базы.")
        logging.error(f"Ошибка поиска альбома: {e}")
    finally:
        await state.set_state(InfoActions.to_start)
        keyboard = ReplyKeyboardMarkup(
            keyboard=kb_got_it, resize_keyboard=True, one_time_keyboard=True
        )
        await message.answer("Возврат к началу", reply_markup=keyboard)


"""
    Поиск исполнителей
"""

@dp.message(InfoActions.search_which, F.text.lower().strip() == 'исполнителя по названию')
async def search_artist_by_name(message: Message, state: FSMContext):
    await message.answer("Хорошо, давайте найдём исполнителя по названию. Напишите название исполнителя")
    await state.set_state(InfoActions.search_artist)

@dp.message(InfoActions.search_artist)
async def get_artist(message: Message, state: FSMContext):
    try:
        artist = message.text.lower().strip()
        conn = await get_db_connection()
        rows = await conn.fetch(
                """
                SELECT 
                    artistName, artistCountry
                FROM Artist
                WHERE artistName = $1
                """, 
                artist
        )
        await conn.close()

        if rows:
            response = "\n\n".join(
                [
                    f"Исполнитель: {row['artistname']}\n"
                    f"Страна: {row['artistcountry']}\n"
                    for row in rows
                ]
            )
            await message.answer(f"Исполнители с этим названием:\n\n")
            await send_long_message(message, response)
        else:
            await message.answer("Нет исполнителей с таким названием")

    except Exception as e:
        await message.answer("Ошибка при получении данных из базы.")
        logging.error(f"Ошибка поиска исполнителя: {e}")
    finally:
        await state.set_state(InfoActions.to_start)
        keyboard = ReplyKeyboardMarkup(
            keyboard=kb_got_it, resize_keyboard=True, one_time_keyboard=True
        )
        await message.answer("Возврат к началу", reply_markup=keyboard)

"""
    Поиск лейблов
"""

@dp.message(InfoActions.search_which, F.text.lower().strip() == 'лейбл по названию')
async def search_label_by_name(message: Message, state: FSMContext):
    await message.answer("Хорошо, давайте найдём лейбл по названию. Напишите название звукозаписывающей компании")
    await state.set_state(InfoActions.search_label)

@dp.message(InfoActions.search_label)
async def get_label(message: Message, state: FSMContext):
    try:
        label = message.text.lower().strip()
        conn = await get_db_connection()
        rows = await conn.fetch(
                """
                SELECT 
                    labelName, labelCountry
                FROM Label
                WHERE labelName = $1
                """, 
                label
        )
        await conn.close()

        if rows:
            response = "\n\n".join(
                [
                    f"Звукозаписывающая компания: {row['labelname']}\n"
                    f"Страна: {row['labelcountry']}\n"
                    for row in rows
                ]
            )
            await message.answer(f"Компании с этим названием:\n\n")
            await send_long_message(message, response)
        else:
            await message.answer("Нет лейблов с таким названием")

    except Exception as e:
        await message.answer("Ошибка при получении данных из базы.")
        logging.error(f"Ошибка поиска лейбла: {e}")
    finally:
        await state.set_state(InfoActions.to_start)
        keyboard = ReplyKeyboardMarkup(
            keyboard=kb_got_it, resize_keyboard=True, one_time_keyboard=True
        )
        await message.answer("Возврат к началу", reply_markup=keyboard)


@dp.message((F.text.lower().strip() == "просмотр коллекции"))
async def view_vinyls_handler(message: Message, state:FSMContext):
    try:
        conn = await get_db_connection()
        user_id = message.from_user.id
        name = await search_user(conn, user_id)

        rows = await conn.fetch(
            """
            SELECT 
                r.recordCond, r.recordSize, r.recordYear,
                a.albumName, ar.artistName, l.labelName
            FROM Record r
            JOIN Album a ON r.albumID = a.albumID
            JOIN Artist ar ON a.artistID = ar.artistID
            JOIN Label l ON r.labelID = l.labelID
            WHERE r.userID = $1
            """, user_id
        )
        await conn.close()
        if rows:
            response = "\n\n".join(
                [
                    f"Исполнитель: {row['artistname']}\n"
                    f"Альбом: {row['albumname']}\n"
                    f"Год: {row['recordyear']}\n"
                    f"Состояние: {row['recordcond']}\n"
                    f"Размер: {row['recordsize']}\n"
                    f"Лейбл: {row['labelname']}"
                    for row in rows
                ]
            )
            await message.answer(f"Вот ваша коллекция, {name}:\n\n")
            await send_long_message(message, response)
        else:
            await message.answer("Ваша коллекция пока пуста.")
    except Exception as e:
        await message.answer("Ошибка при получении данных из базы.")
        logging.error(f"Ошибка просмотра коллекции: {e}")
    finally:
        await message.answer("Как вам моя работа? Пожалуйста, поставьте оценку от 1 до 10!")
        await state.set_state(RegistrationForm.form)

@dp.message(RegistrationForm.form)
async def get_rating(message: Message, state: FSMContext):
    try:
        value = int(message.text)
        user_id = message.from_user.id
        conn = await get_db_connection()
        await conn.fetchrow("""
                            INSERT INTO Rating (userValue, userID)
                            VALUES ($1, $2)
                            """, 
                            value, user_id)
        await conn.close()

        await message.answer("Спасибо за оценку!")
        await state.set_state(InfoActions.to_start)
        keyboard = ReplyKeyboardMarkup(
                keyboard=kb_got_it, resize_keyboard=True, one_time_keyboard=True
            )
        await message.answer("Возврат к началу", reply_markup=keyboard)
    except Exception as e:
        await message.answer("Ошибка получения оценки. Проверьте формат. Это должно быть число от 1 до 10")
        logging.error(f"Ошибка получения оценки: {e}")

"""
    Редактирование записей. Пример на исполнителе
"""
@dp.message(F.text.lower().strip() == "редактировать информацию")
async def edit_info_handler(message: Message, state: FSMContext):
    texts = {
        "artist": "Исполнитель",
    }

    builder = InlineKeyboardBuilder()
    builder.button(text=texts["artist"], callback_data="edit_artist")
    builder.adjust(1)
    await message.answer(
        "Что будем редактировать?", reply_markup=builder.as_markup()
    )
    await state.set_state(InfoActions.edit_which)

@dp.message(InfoActions.edit_which, F.text.lower().strip() == "исполнитель")
@dp.callback_query(F.data == 'edit_artist')
async def which_artist(message: Message, state: FSMContext):
    await message.answer(
        "Информацию о каком исполнителе изменим?"
    )
    await state.set_state(InfoActions.edit_show_artist)

@dp.message(InfoActions.edit_show_artist)
async def show_artist(message: Message, state: FSMContext):
    try:
        conn = await get_db_connection()
        artist_name = message.text.lower().strip()
        artist = await search_artist(conn, artist_name)
        if artist:
            await info_artist(conn, message, artist_name)
            await conn.close()
            await message.answer("Введите обновлённые данные в формате: Название, Страна")
            await state.update_data(artist_id = artist['artistid'])
            await state.set_state(InfoActions.edit_artist)
        else:
            await message.answer("Такого исполнителя нет в базе!")
            await state.set_state(InfoActions.to_start)
    except Exception as e:
        await message.answer("Ошибка при получении данных из базы.")
        logging.error(f"Ошибка получении информации об исполнителе: {e}")

@dp.message(InfoActions.edit_artist)
async def edit_artist(message: Message, state: FSMContext):
    try:
        data = message.text.split(', ')
        artist_name, artist_country = data[0].lower().strip(), data[1].lower().strip()
        st_data = await state.get_data()
        artist_id = st_data.get("artist_id")
        conn = await get_db_connection()
        await conn.fetchrow(
            """
            UPDATE Artist
            SET artistName = $1,
                artistCountry = $2
            WHERE artistID = $3
            """,
            artist_name, artist_country, artist_id
        )
        await message.answer("Исполнитель успешно обновлён")
        await state.set_state(InfoActions.to_start)
        keyboard = ReplyKeyboardMarkup(
                keyboard=kb_got_it, resize_keyboard=True, one_time_keyboard=True
            )
        await message.answer("Возврат к началу", reply_markup=keyboard)
    except asyncpg.UniqueViolationError as e:
        await message.answer("Ошибка! Исполнитель с такими характеристиками уже существует в коллекции.")
        logging.error(f"Ошибка добавления исполнителя: {e}")

    except Exception as e:
        await message.answer("Ошибка при добавлении исполнителя. Попробуйте снова.")
        logging.error(f"Ошибка добавления исполнителя: {e}")


"""
    Подбор музыки с помощью GigaChat
"""

def start_GigaChat():
    llm = GigaChat(
        credentials=GigaChatKey,
        scope="GIGACHAT_API_PERS",
        model="GigaChat",
        verify_ssl_certs=False, 
        streaming=False,
    )
    return llm

@dp.message(F.text.lower().strip()=="подобрать музыку по интересам")
async def music_by_interest(message: Message, state: FSMContext):
    await message.answer("Супер! Помогу подобрать похожую музыку. Напишите названия исполнителей, "
                         "альбомов или песен, которые вам нравятся. Также можете указать любимый жанр.")
    await state.set_state(AITalks.get_message)

@dp.message(AITalks.get_message)
async def get_interests(message: Message, state: FSMContext):
    try:
        text = message.text
        await message.answer("Принято. Это займёт несколько секунд...")
        llm = start_GigaChat()
        answer_template = """
                    Ты - эксперт в музыке, готов помочь подобрать музыку по интересам. Вот диалог с пользователем:
                    История диалога:
                    {history}

                    Пользователь: Подбери музыкальные альбомы, исполнителей или песни, похожие на это: {input}
                    Полный ответ:
                    """
        answer_prompt = PromptTemplate(
            input_variables=["history", "input"],
            template=answer_template
        )

        summary_template = """
                            Ты - эксперт в краткости. 
                            Учитывая историю диалога, сократи следующий текст, сохраняя суть, сделай выжимку.
                            История диалога:
                            {history}

                            Текст для сокращения:
                            {long_text}

                            Краткий ответ:
                           """
        summary_prompt = PromptTemplate(
            input_variables=["history", "long_text"],
            template=summary_template

        )

        memory = ConversationBufferMemory(
            memory_key="history",
            return_messages=True
        )


        answer_chain = answer_prompt | llm
        first_result = answer_chain.invoke({
            "history": memory.load_memory_variables({})["history"],
            "input": text
        }).content
        memory.save_context({"input": text}, {"full_answer": first_result})

        summary_chain = summary_prompt | llm
        second_result = summary_chain.invoke({
            "history": memory.load_memory_variables({})["history"],
            "long_text": first_result
        }).content
        memory.save_context({"long_text": first_result}, {"short_answer": second_result})

        await message.answer(html.bold("Полный ответ:"))
        await send_long_message(message, first_result)
        await message.answer(html.bold("Краткий ответ:"))
        await send_long_message(message, second_result)

    except Exception as e:
        await message.answer("Произошла неизвестная ошибка")
        logging.error(f"Ошибка генерации ответа: {e}")
    finally:
        await state.set_state(InfoActions.to_start)
        keyboard = ReplyKeyboardMarkup(
                keyboard=kb_got_it, resize_keyboard=True, one_time_keyboard=True
            )
        await message.answer("Возврат к началу", reply_markup=keyboard)


@dp.message(Command("on"))
async def on_notifications(message: Message):
    conn = await get_db_connection()
    await conn.execute("UPDATE Users SET notif = TRUE WHERE userID = $1", (message.from_user.id))
    await conn.close()

    await message.answer('Напоминания послушать музыку активированы!')

@dp.message(Command("off"))
async def off_notifications(message: Message):
    conn = await get_db_connection()
    await conn.execute("UPDATE Users SET notif = False WHERE userID = $1", (message.from_user.id))
    await conn.close()

    await message.answer('Напоминания отключены!')

async def send_msg(dp):
    conn = await get_db_connection()
    try: 
        async with conn.transaction():
            async for row in conn.cursor("SELECT * FROM Users WHERE notif = TRUE"): 
                try:
                    await bot.send_message(chat_id=row[0], text='Время послушать музыку!')
                except Exception as e:
                    logging.error(f"Ошибка отправки сообщения пользователю {row[0]}: {e}")
    finally:
        if conn:
            await conn.close()


@dp.message()
async def any_text(message: Message):
    await message.answer("Ничего не понял. Нажмите, пожалуйста, кнопку!")

logging_middleware = UserActionLoggingMiddleware()
dp.message.middleware(logging_middleware)
dp.callback_query.middleware(logging_middleware)
dp.message.middleware(RegistrationCheckMiddleware())




async def main() -> None:
    scheduler = AsyncIOScheduler(timezone='Europe/Moscow')
    job = scheduler.add_job(send_msg, 'interval', minutes=2, args=(dp,))
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())