import os
import random
import asyncio
from typing import List, Dict, Any

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext

from database import db
from security import IsAuthorized
from states.states import InteractionState
from keyboards.keyboards import (
    get_main_menu_keyboard,
    get_cancel_keyboard,
    get_interaction_action_keyboard,
    get_interaction_account_choice_keyboard
)
from services.tiktok_service import TikTokService

router = Router()
router.message.filter(IsAuthorized())
router.callback_query.filter(IsAuthorized())

@router.callback_query(F.data == "mass_interaction")
async def mass_interaction_start(callback: CallbackQuery, state: FSMContext):
    """Entry point from main menu: choose which accounts to interact with."""
    await state.clear()
    accounts = await db.get_all_accounts()
    if not accounts:
        await callback.answer("❌ Нет подключенных аккаунтов.", show_alert=True)
        return

    text = (
        "💥 **Лайки и комментарии на видео TikTok**\n\n"
        "Выберите, с какого аккаунта выполнить действие, или запустите со всех сразу:"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_interaction_account_choice_keyboard(accounts),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("single_interact_"))
async def single_interact_start(callback: CallbackQuery, state: FSMContext):
    """Entry point from single account menu."""
    await state.clear()
    acc_id = int(callback.data.split("_")[2])
    await state.update_data(target_mode="single", target_acc_id=acc_id)
    await state.set_state(InteractionState.waiting_for_url)

    text = (
        "🔗 **Отправьте ссылку на видео в TikTok**\n\n"
        "Формат: `https://www.tiktok.com/@username/video/1234567890`"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_cancel_keyboard("back_to_main"),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("target_acc_"))
async def process_target_account(callback: CallbackQuery, state: FSMContext):
    target = callback.data.split("target_acc_")[1]
    if target == "all":
        await state.update_data(target_mode="all")
    else:
        await state.update_data(target_mode="single", target_acc_id=int(target))

    await state.set_state(InteractionState.waiting_for_url)
    text = (
        "🔗 **Отправьте ссылку на видео в TikTok**\n\n"
        "Формат: `https://www.tiktok.com/@username/video/1234567890`"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_cancel_keyboard("back_to_main"),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.message(InteractionState.waiting_for_url)
async def process_video_url(message: Message, state: FSMContext):
    url = (message.text or "").strip()
    if "tiktok.com" not in url:
        await message.answer(
            "⚠️ Пожалуйста, отправьте корректную ссылку TikTok.\n"
            "Пример видео: `https://www.tiktok.com/@username/video/7123456789012345678`\n"
            "Или ссылка на профиль (бот сам выберет последнее видео): `https://www.tiktok.com/@username`"
        )
        return

    await state.update_data(video_url=url)
    await state.set_state(InteractionState.waiting_for_action)

    text = (
        "🎯 **Выберите действие для этого видео:**\n\n"
        f"📹 Видео: {url}"
    )
    await message.answer(
        text,
        reply_markup=get_interaction_action_keyboard(),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.in_(["action_like", "action_comment", "action_both"]))
async def process_action_choice(callback: CallbackQuery, state: FSMContext):
    action = callback.data
    await state.update_data(action_type=action)

    if action == "action_like":
        # Start immediately without asking for comment text
        await callback.answer()
        await execute_interaction(callback.message, state, do_like=True, comment_text="")
    else:
        # Needs comment text
        await state.set_state(InteractionState.waiting_for_comment)
        text = (
            "💬 **Введите текст комментария:**\n\n"
            "💡 _Совет: пишите естественные фразы (например: 'Классное видео! 🔥', 'Топ контент 👍'). Не отправляйте случайный набор букв (вроде 'asdfgh'), так как спам-фильтр TikTok автоматически скрывает такой текст._\n\n"
            "_(Если запускаете для нескольких аккаунтов, вы можете ввести несколько вариантов текста через символ `;` или с новой строки — бот выберет случайный для каждого аккаунта)_"
        )
        await callback.message.edit_text(
            text,
            reply_markup=get_cancel_keyboard("back_to_main"),
            parse_mode="Markdown"
        )
        await callback.answer()

@router.message(InteractionState.waiting_for_comment)
async def process_comment_text(message: Message, state: FSMContext):
    raw_text = (message.text or "").strip()
    if not raw_text:
        await message.answer("❌ Текст комментария не может быть пустым.")
        return

    data = await state.get_data()
    action = data.get("action_type", "action_both")
    do_like = action in ["action_like", "action_both"]

    await execute_interaction(message, state, do_like=do_like, comment_text=raw_text)

async def execute_interaction(message: Message, state: FSMContext, do_like: bool, comment_text: str):
    data = await state.get_data()
    video_url = data.get("video_url")
    target_mode = data.get("target_mode", "all")
    target_acc_id = data.get("target_acc_id")

    all_accounts = await db.get_all_accounts()
    if target_mode == "single":
        accounts_to_run = [a for a in all_accounts if a["id"] == target_acc_id]
    else:
        accounts_to_run = all_accounts

    if not accounts_to_run:
        await message.answer("❌ Аккаунты не найдены.")
        await state.clear()
        return

    # Parse potential multiple comment options
    comment_options = [c.strip() for c in comment_text.replace("\n", ";").split(";") if c.strip()]
    if not comment_options:
        comment_options = [comment_text]

    status_msg = await message.answer(
        f"⏳ **Запуск взаимодействия...**\n"
        f"👥 Аккаунтов в очереди: **{len(accounts_to_run)}**\n"
        f"📹 Видео: {video_url}\n\n"
        f"Пожалуйста, подождите...",
        parse_mode="Markdown"
    )

    results = []
    for idx, acc in enumerate(accounts_to_run, 1):
        display_name = acc.get("name") or f"Аккаунт {acc['id']}"
        await status_msg.edit_text(
            f"⏳ **Обработка ({idx}/{len(accounts_to_run)}):** {display_name}...\n"
            f"📹 {video_url}",
            parse_mode="Markdown"
        )

        chosen_comment = random.choice(comment_options) if comment_options else ""
        success, msg, shot_path = await TikTokService.interact_with_video(
            cookies_json=acc["cookies_json"],
            video_url=video_url,
            proxy_str=acc.get("proxy") or "",
            do_like=do_like,
            comment_text=chosen_comment
        )

        results.append((display_name, success, msg))

        if shot_path and os.path.exists(shot_path):
            try:
                photo_file = FSInputFile(shot_path)
                caption = f"📸 **{display_name}**:\n{msg}"
                await message.answer_photo(photo=photo_file, caption=caption, parse_mode="Markdown")
                try:
                    os.remove(shot_path)
                except Exception:
                    pass
            except Exception as ex:
                print(f"Error sending screenshot: {ex}")

        # Human-like cooldown between accounts if multiple
        if idx < len(accounts_to_run):
            wait_sec = random.randint(15, 30)
            await status_msg.edit_text(
                f"⏳ Завершено для {display_name}.\n"
                f"💤 Пауза между аккаунтами {wait_sec} сек...",
                parse_mode="Markdown"
            )
            await asyncio.sleep(wait_sec)

    summary_lines = ["🏁 **Результаты взаимодействия с видео:**\n"]
    for name, ok, note in results:
        icon = "✅" if ok else "❌"
        summary_lines.append(f"{icon} **{name}**: {note}")

    summary_text = "\n".join(summary_lines)
    keyboard = get_main_menu_keyboard(all_accounts)
    await message.answer(summary_text, reply_markup=keyboard, parse_mode="Markdown")
    await state.clear()
