import json
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from security import IsAuthorized

from database import db
from keyboards.keyboards import get_main_menu_keyboard, get_cancel_keyboard
from states.states import AddAccountState
from services.tiktok_service import TikTokService
from config import mask_proxy

router = Router()
router.message.filter(IsAuthorized())
router.callback_query.filter(IsAuthorized())

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    accounts = await db.get_all_accounts()
    keyboard = get_main_menu_keyboard(accounts)
    
    total = len(accounts)
    active = sum(1 for a in accounts if a.get("is_active"))
    
    text = (
        "👋 **Главное меню TikTok Manager**\n\n"
        f"📊 Подключено аккаунтов: **{total}** (Активных: {active})\n\n"
        "Выберите аккаунт из списка ниже для управления или действие:"
    )
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data == "back_to_main")
async def back_to_main_handler(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    accounts = await db.get_all_accounts()
    keyboard = get_main_menu_keyboard(accounts)
    
    total = len(accounts)
    active = sum(1 for a in accounts if a.get("is_active"))
    
    text = (
        "👋 **Главное меню TikTok Manager**\n\n"
        f"📊 Подключено аккаунтов: **{total}** (Активных: {active})\n\n"
        "Выберите аккаунт из списка ниже для управления или действие:"
    )
    if callback.message:
        try:
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        except Exception:
            await callback.message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "add_account")
async def add_account_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddAccountState.waiting_for_name)
    text = (
        "➕ **Добавление нового аккаунта**\n\n"
        "Шаг 1/3: Введите название для аккаунта (например: *Акк 1*, *Крипта US*, *Личный*):"
    )
    await callback.message.edit_text(text, reply_markup=get_cancel_keyboard("back_to_main"), parse_mode="Markdown")
    await callback.answer()

@router.message(AddAccountState.waiting_for_name)
async def process_account_name(message: Message, state: FSMContext):
    name = message.text.strip()
    await state.update_data(name=name)
    await state.set_state(AddAccountState.waiting_for_cookies)
    
    text = (
        f"✅ Название: **{name}**\n\n"
        "Шаг 2/3: Отправьте **Cookies** от аккаунта TikTok.\n"
        "_(Экспортируйте через расширение Cookie-Editor в формате JSON или отправьте строку sessionid)_:"
    )
    await message.answer(text, reply_markup=get_cancel_keyboard("back_to_main"), parse_mode="Markdown")

@router.message(AddAccountState.waiting_for_cookies)
async def process_account_cookies(message: Message, state: FSMContext):
    # Check if document was uploaded (e.g. cookies.json file)
    if message.document:
        file = await message.bot.get_file(message.document.file_id)
        file_bytes = await message.bot.download_file(file.file_path)
        cookies_raw = file_bytes.read().decode("utf-8")
    else:
        cookies_raw = message.text or ""

    if not cookies_raw.strip():
        await message.answer("❌ Пустые cookies. Пожалуйста, отправьте текст или файл JSON с cookies.")
        return

    await state.update_data(cookies=cookies_raw)
    await state.set_state(AddAccountState.waiting_for_proxy)
    
    text = (
        "✅ Cookies получены!\n\n"
        "Шаг 3/3: Отправьте **прокси** для этого аккаунта в формате:\n"
        "`ip:port:user:password` или `http://user:pass@ip:port`\n\n"
        "_(Если прокси не нужен, отправьте знак минуса `-` или слово `пропустить`)_:"
    )
    await message.answer(text, reply_markup=get_cancel_keyboard("back_to_main"), parse_mode="Markdown")

@router.message(AddAccountState.waiting_for_proxy)
async def process_account_proxy(message: Message, state: FSMContext):
    proxy_raw = message.text.strip()
    if proxy_raw.lower() in ["-", "пропустить", "нет", "none", "no"]:
        proxy = ""
    else:
        proxy = proxy_raw

    data = await state.get_data()
    name = data["name"]
    cookies = data["cookies"]

    msg = await message.answer("🔄 Проверяю сессию и данные аккаунта в TikTok... Пожалуйста, подождите.")
    
    # Verify in TikTok
    try:
        is_valid, stats = await TikTokService.verify_session_and_get_profile(cookies, proxy)
    except Exception:
        await state.clear()
        await msg.edit_text("❌ Не удалось проверить сессию. Проверьте формат cookies и прокси и попробуйте снова.")
        return
    
    # Save to database
    acc_id = await db.add_account(name=name, cookies_json=cookies, proxy=proxy, username=stats.get("username", ""))
    if is_valid:
        await db.update_account_stats(
            account_id=acc_id,
            username=stats.get("username", ""),
            avatar_url=stats.get("avatar_url", ""),
            followers=stats.get("followers", 0),
            views=stats.get("views", 0),
            likes=stats.get("likes", 0),
            video_count=stats.get("video_count", 0),
            is_active=1
        )
    
    await state.clear()
    
    status_text = "🟢 Сессия активна!" if is_valid else "⚠️ Добавлен (но сессия не подтверждена или требует проверки)."
    
    result_text = (
        f"🎉 **Аккаунт успешно сохранен!**\n\n"
        f"🏷 Имя: **{name}**\n"
        f"👤 TikTok: `@{stats.get('username') or 'Не указан'}`\n"
        f"🌐 Прокси: `{mask_proxy(proxy)}`\n"
        f"Статус: {status_text}"
    )
    
    accounts = await db.get_all_accounts()
    await msg.edit_text(result_text, reply_markup=get_main_menu_keyboard(accounts), parse_mode="Markdown")
