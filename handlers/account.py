from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from security import IsAuthorized

from database import db
from keyboards.keyboards import get_account_menu_keyboard, get_main_menu_keyboard
from config import mask_proxy

router = Router()
router.message.filter(IsAuthorized())
router.callback_query.filter(IsAuthorized())

@router.callback_query(F.data.startswith("account_"))
async def account_card_handler(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    acc_id = int(callback.data.split("_")[1])
    acc = await db.get_account_by_id(acc_id)
    
    if not acc:
        await callback.answer("❌ Аккаунт не найден", show_alert=True)
        return

    name = acc.get("name") or f"Аккаунт {acc['id']}"
    username = acc.get("username") or "не указан"
    followers = acc.get("followers_count", 0)
    views = acc.get("views_count", 0)
    likes = acc.get("likes_count", 0)
    status_icon = "🟢 Активен" if acc.get("is_active") else "🔴 Требует обновления куков"
    proxy_info = mask_proxy(acc.get("proxy", ""))

    text = (
        f"📱 **Аккаунт: {name}** (@{username})\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **Статистика:**\n"
        f"👥 Подписчики: **{followers:,}**\n"
        f"👁 Просмотры: **{views:,}**\n"
        f"❤️ Лайки: **{likes:,}**\n"
        f"🌐 Прокси: `{proxy_info}`\n"
        f"Статус: {status_icon}\n"
        f"━━━━━━━━━━━━━━━━━━━"
    )
    
    keyboard = get_account_menu_keyboard(acc_id)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("delete_acc_"))
async def delete_account_handler(callback: CallbackQuery):
    acc_id = int(callback.data.split("_")[2])
    await db.delete_account(acc_id)
    await callback.answer("🗑 Аккаунт удален", show_alert=True)
    
    accounts = await db.get_all_accounts()
    text = (
        "👋 **Главное меню TikTok Manager**\n\n"
        f"📊 Подключено аккаунтов: **{len(accounts)}**\n\n"
        "Выберите аккаунт из списка ниже для управления или действие:"
    )
    await callback.message.edit_text(text, reply_markup=get_main_menu_keyboard(accounts), parse_mode="Markdown")
