# Бот для хранения виниловых пластинок
Телеграм-бот для взаимодействия с базой данных для хранения информации о частных коллекциях виниловых пластинок. Многопользовательский, поддерживает добавление, редактирование и удаление информации об исполнителях, альбомах, лейблах и имеющихся пластинках. Помимо этого, с помощью GigaChat API позволяет пользователю подобрать музыку по интересам.

## Установка программы
1. Установка PostgreSQL<br/>Linux (Ubuntu): <br/>`sudo apt update` <br/>`sudo apt install postgresql postgresql-contrib`<br/>После установки запустите службу PostgreSQL:<br/>`sudo systemctl start postgresql`<br/>`sudo systemctl enable postgresql`
<br/>MacOS: используйте Homebrew для установки:<br/>`brew install postgresql`<br/>`brew services start postgresql`<br/>Windows: скачайте установщик с официального сайта PostgreSQL и следуйте инструкциям.
2. Создание базы данных (см. ниже)
2. `python -m venv venv` - установка виртуального окружения.
3. Активация окружения: <br/> Windows: `.\venv\Scripts\activate`<br/> MacOS/Linux: `source ./venv/bin/activate`.
4. `pip install -r requirements.txt` - установка необходимых библиотек.
5. В корневой папке создайте файл `.env` и напишите там свои данные в формате: <br/>`botToken = 'токен вашего бота'`<br/>`GigaChatKey = 'ключ авторизации Gigachat API'`<br/>`DB_NAME = название вашей базы данных`<br/>`DB_USER = имя пользователя для базы данных`<br/>`DB_PASSWORD = пароль пользователя базы данных`<br/>`DB_HOST = адрес хоста`<br/>`DB_PORT = порт`

## Создание базы данных
Cоздайте базу данных с помощью скрипта `VinylBot_database.sql`. 
1. Подключитесь к PostgreSQL: <br/>Linux/MacOS: `sudo -u postgres psql` <br/>Windows: используйте psql из командной строки или pgAdmin.
2. Создайте новую базу данных: <br/>В консоли psql выполните: <br/>`CREATE DATABASE your_database_name;
\q`
3. Запустите SQL-скрипт для создания структуры базы данных: <br/>`psql -U postgres -d your_database_name -f VinylBot_database.sql`

## Запуск программы
1. В терминале напишите следующую команду:
`python main.py`
## Добавление новых зависимостей
1. `pip freeze > requirements.txt`