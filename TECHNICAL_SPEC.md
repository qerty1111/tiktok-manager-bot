# Техническое задание и Архитектурная документация: TikTok Manager Bot

> **Назначение документа**: Руководство по архитектуре, логике работы, развертыванию и поддержке проекта для разработчика.

---

## 1. Обзор проекта и стек технологий

**TikTok Manager Bot** — это асинхронный сервис автоматизации аккаунтов TikTok с управлением через Telegram-бота. Бот позволяет централизованно управлять фермой TikTok-аккаунтов: загружать видео по расписанию, менять био, никнеймы и аватарки, ставить лайки и публиковать комментарии с обходом систем защиты TikTok.

### Технологический стек:
* **Язык**: Python 3.10+
* **Telegram Framework**: `aiogram 3.x` (FSM, Routers, Inline Keyboards, Magic Filters)
* **Браузерная автоматизация**: `Playwright (async_api)` + `playwright-stealth`
* **Канал браузера**: Google Chrome (`channel="chrome"`, `headless=False` / `Xvfb`)
* **База данных**: SQLite через `aiosqlite` (асинхронный драйвер)
* **Капча-резолвер**: `CapSolver API` (модули `slider_1` для пазлов и `rotate_2` для 3D-вращения кругов)
* **Конфигурация**: `python-dotenv`, `pydantic`

---

## 2. Архитектура проекта

```
tiktok_bot/
├── main.py                     # Точка входа, запуск polling aiogram, подключение роутеров
├── config.py                   # Загрузка .env, системные пути, валидация конфигурации
├── requirements.txt            # Зафиксированные версии зависимостей
├── .env.example                # Шаблон конфигурации окружения
├── .gitignore                  # Исключения (база данных, медиа, токены, логи)
│
├── database/
│   └── db.py                   # Инициализация SQLite, асинхронные CRUD-методы аккаунтов
│
├── handlers/                   # Обработчики Telegram-команд и FSM сценариев
│   ├── admin.py                # Главное меню, авторизация администратора (/start, /menu)
│   ├── accounts.py             # Добавление/удаление аккаунтов, парсинг cookies и proxy
│   ├── profile.py              # Редактирование профиля (Bio, Nickname, Аватарка)
│   ├── upload.py               # Загрузка и публикация видео в TikTok Studio
│   └── interaction.py          # Взаимодействие с видео (Лайки, Комментарии, Single/Mass)
│
├── services/                   # Бизнес-логика и автоматизация
│   ├── tiktok_service.py       # Ядро взаимодействия с TikTok через Playwright
│   └── captcha_solver.py       # Интеграция с CapSolver (слайдеры, whirl-вращение)
│
├── keyboards/                  # Инлайн-клавиатуры для диалогов
│   └── inline.py               # Динамические клавиатуры списков аккаунтов, действий, отмены
│
└── states/                     # Машины состояний (aiogram StatesGroup)
    ├── account_states.py       # Состояния добавления аккаунта
    ├── profile_states.py       # Состояния редактирования био/ника/аватарки
    ├── upload_states.py        # Состояния загрузки видео
    └── interaction_states.py   # Состояния выбора видео, лайка и текста комментария
```

---

## 3. Функциональные модули

### 3.1. Управление аккаунтами (`handlers/accounts.py`, `database/db.py`)
* **Авторизация**: По cookies (поддерживаются как JSON-экспорты из расширений EditThisCookie / Cookie-Editor, так и raw cookie-строки).
* **Прокси**: Индивидуальный прокси для каждого аккаунта (`http://user:pass@ip:port` или `socks5://...`). Бот автоматически парсит формат и передает в Playwright context.
* **База данных**: Хранение в SQLite (`data/bot.db`). Поля: `id`, `name`, `username`, `cookies_json`, `proxy`, `status`, `created_at`.

### 3.2. Редактирование профиля (`services/tiktok_service.py` -> `update_profile_bio`, `upload_avatar`)
* **Смена никнейма и описания (Bio)**: Открытие модального окна профиля, заполнение формы, сохранение и обработка системного ответа.
* **Смена аватарки**:
  * Загрузка файла через скрытый input (`input[type="file"]`).
  * Обработка модального окна кадрирования TikTok (Crop Modal): ожидание прогрузки ползунка масштабирования, клик по кнопке «Apply» («Применить»).
  * Ожидание закрытия модалки и клик на основную кнопку «Save».
  * Валидация успешности по перехвату POST-запроса `/passport/web/account/info/update/` или исчезновению формы.

### 3.3. Публикация видео (`services/tiktok_service.py` -> `upload_video`)
* Переход в веб-студию загрузки: `https://www.tiktok.com/tiktokstudio/upload`.
* Загрузка MP4 файла через `file_chooser` или `set_input_files`.
* Заполнение описания с хэштегами и упоминаниями.
* Ожидание 100% готовности видео (индикатор загрузки и превью обложки).
* Нажатие кнопки «Post» («Опубликовать») и валидация успешного редиректа на страницу контента (`/manage/content`).

### 3.4. Лайки и комментарии (`services/tiktok_service.py` -> `interact_with_video`)
* **Гибкий таргетинг**: Поддерживаются прямые ссылки на видео (`https://www.tiktok.com/@user/video/12345`) и ссылки на профиль (бот автоматически парсит и находит самое последнее опубликованное видео автора).
* **Одиночный и массовый режим**: Возможность выполнить действие от одного выбранного аккаунта или автоматически запустить по всем добавленным аккаунтам с рандомизированными паузами (15–30 сек) между ними.
* **Ротация комментариев**: Возможность указать несколько вариантов комментариев через точку с запятой (`;`) или с новой строки — бот распределяет случайный комментарий на каждый аккаунт.
* **Фото-отчет**: После каждого действия бот делает скриншот страницы с результатом и отправляет его администратору в Telegram.

---

## 4. Решенные технические нюансы (Critical Knowledge)

При разработке автоматизации под TikTok были решены сложные защитные барьеры платформы. Новому разработчику важно понимать их суть:

### 1. Защита SecSDK TicketGuard (код ответа 1104)
* **Проблема**: В режиме `headless=True` TikTok активирует SecSDK. Браузер отправляет запрос на лайк или комментарий, сервер возвращает статус HTTP 200, но с заголовком `tt-ticket-guard-result: 1104` и пустым телом — сервер **тихо отбрасывает действие**, не сохраняя его в базе.
* **Решение**: Использование реального бинарника Chrome (`channel="chrome"`) в видимом режиме (`headless=False`). На Linux серверах запускается через виртуальный дисплей **Xvfb** (см. раздел развертывания).

### 2. Редактор комментариев Draft.js
* **Проблема**: Поле комментариев TikTok на ПК — это не `<textarea>`, а фреймворк Draft.js. Если кликнуть по внешнему блоку `div[data-e2e="comment-input"]`, текст вводится в виртуальный DOM, но кнопка `Post` остается серой и неактивной.
* **Решение**: Фокусировка направлена строго на внутренний редактируемый элемент:
  `div.public-DraftEditor-content[role="textbox"]`.
  Кнопка отправки нажимается через реальное наведение и клик мыши по координатам `div[data-e2e="comment-post"]`.

### 3. Определение статуса лайка через WAI-ARIA
* **Проблема**: SVG иконка сердца в веб-плеере TikTok не меняет цвет атрибута `fill` напрямую (там всегда указан `fill="currentColor"`). Проверка через CSS-цвета дает ложные сбои.
* **Решение**: Использован стандарт доступности W3C, которому строго следует TikTok:
  * Не лайкнуто: `div[data-e2e="like-icon"][aria-pressed="false"]` (или `aria-label="Like video"`)
  * Лайкнуто: `div[data-e2e="like-icon"][aria-pressed="true"]` (или `aria-label="Unlike video"`)

### 4. Автоматическое решение капчи (CapSolver)
* **Проблема**: TikTok генерирует 2 типа капчи: обычный горизонтальный пазл-слайдер и 3D-вращение концентрических кругов (Whirl).
* **Решение**:
  * Если появляется Whirl, бот пытается до 4 раз обновить капчу (`#captcha_refresh_button`), чтобы получить простой пазл.
  * Если остается Whirl, CapSolver формирует композитное изображение для модуля `rotate_2` и крутит слайдер до нужного градуса.
  * Добавлен цикл ожидания отрисовки (`track_data retry`), чтобы предотвратить ошибку "Could not calculate track geometry".

### 5. Лимиты редактирования профиля (`status_code: 3002284`)
* **Проблема**: При частой смене данных профиля TikTok выдает ошибку `"Slow down, you are editing too fast"`.
* **Решение**: Бот перехватывает код `3002284` и корректно сообщает пользователю о необходимости сделать паузу на 15–20 минут.

### 6. Теневая премодерация комментариев (`status: 2`)
* **Проблема**: Свежие аккаунты без прогрева при отправке комментариев получают от TikTok статус `status: 2` (на рассмотрении спам-фильтром). Автор видит свой комментарий, но для чужих пользователей он скрыт.
* **Решение**: В бота внедрена валидация осмысленного текста. Аккаунты требуют минимального предварительного прогрева (просмотр ленты FYP).

---

## 5. Инструкция по развертыванию на сервере (VPS Ubuntu / Debian)

### Шаг 1. Установка системных зависимостей
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git xvfb libgbm-dev wget curl
```

### Шаг 2. Установка Google Chrome
```bash
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo dpkg -i google-chrome-stable_current_amd64.deb
sudo apt --fix-broken install -y
```

### Шаг 3. Клонирование репозитория и окружение
```bash
git clone <URL_ВАШЕГО_РЕПОЗИТОРИЯ> /root/tiktok_bot
cd /root/tiktok_bot

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

playwright install chromium
playwright install-deps
```

### Шаг 4. Настройка `.env`
Скопируйте пример и укажите ваши ключи:
```bash
cp .env.example .env
nano .env
```
Заполните параметры:
```ini
BOT_TOKEN=8954915514:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ADMIN_IDS=123456789
CAPSOLVER_API_KEY=CAP-xxxxxxxxxxxxxxxxxxxxxxxxxxxx
DATABASE_PATH=data/bot.db
```

### Шаг 5. Настройка службы Systemd с виртуальным экраном (Xvfb)
Поскольку TikTok блокирует headless-режим, на сервере без монитора используется `xvfb-run`, создающий виртуальный дисплей:

Создайте файл службы:
```bash
sudo nano /etc/systemd/system/tiktok_bot.service
```

Вставьте конфигурацию:
```ini
[Unit]
Description=TikTok Manager Telegram Bot Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/tiktok_bot
Environment="PATH=/root/tiktok_bot/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/usr/bin/xvfb-run --auto-servernum --server-args="-screen 0 1440x900x24" /root/tiktok_bot/venv/bin/python3 /root/tiktok_bot/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Запустите и активируйте службу:
```bash
sudo systemctl daemon-reload
sudo systemctl enable tiktok_bot
sudo systemctl start tiktok_bot
sudo systemctl status tiktok_bot
```

Просмотр логов работы в реальном времени:
```bash
journalctl -u tiktok_bot -f
```

---

## 6. Чек-лист для разработчика, принимающего проект

1. **Прокси**: Всегда используйте качественные приватные резидентские или мобильные прокси. Датацентровые прокси повышают риск капчи и премодерации (`status: 2`).
2. **Сессии Cookies**: Cookies периодически устаревают (обычно живут от 2 недель до нескольких месяцев). При ошибках авторизации достаточно обновить поле `cookies_json` в базе через кнопку «Добавить / Обновить аккаунт».
3. **CapSolver баланс**: Для автоматического решения пазлов убедитесь, что на аккаунте CapSolver есть средства. Решение одного пазла стоит доли цента (~$0.001).
4. **Обновления Playwright / Chrome**: При обновлении версии Chrome на сервере не забывайте запускать `playwright install chromium`.
