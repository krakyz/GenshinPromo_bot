# Обновленный конфигурационный файл с дополнительными настройками

import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_IDS = list(map(int, os.getenv('ADMIN_IDS', '').split(','))) if os.getenv('ADMIN_IDS') else []
DATABASE_PATH = os.getenv('DATABASE_PATH', 'genshin_codes.db')

# Дополнительные настройки для изображений
IMAGES_DIR = os.getenv('IMAGES_DIR', 'images')
MAX_IMAGE_SIZE = int(os.getenv('MAX_IMAGE_SIZE', '10485760'))  # 10MB по умолчанию

# Создаем папку для изображений если её нет
if not os.path.exists(IMAGES_DIR):
    os.makedirs(IMAGES_DIR)

# Валидация конфигурации
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не установлен в переменных окружения")

if not ADMIN_IDS:
    raise ValueError("ADMIN_IDS не установлены в переменных окружения")