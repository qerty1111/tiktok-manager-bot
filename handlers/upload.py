import os
import asyncio
from pathlib import Path
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from security import IsAuthorized

from database import db
from config import MEDIA_DIR
from keyboards.keyboards import (
    get_confirm_upload_keyboard,
    get_confirm_mass_upload_keyboard,
    get_cancel_keyboard,
    get_account_menu_keyboard,
    get_main_menu_keyboard
)
from states.states import UploadSingleState, UploadAllState
from services.tiktok_service import TikTokService

router = Router()
router.message.filter(IsAuthorized())
router.callback_query.filter(IsAuthorized())

# ==================== ОДИНОЧНАЯ ЗАГРУЗКА В АККАУНТ ====================

@router.callback_query(F.data.startswith("upload_single_"))
async def upload_single_start(callback: CallbackQuery, state: FSMContext):
    acc_id = int(callback.data.split("_")[2])
    await state.clear()
    await state.update_data(account_id=acc_id)
    await state.set_state(UploadSingleState.waiting_for_video)
    
    text = (
        "🎬 **Загрузка видео в аккаунт**\n\n"
        "Шаг 1/3: **Отправьте видео файл** в чат (как видео или документом):"
    )
    await callback.message.edit_text(text, reply_markup=get_cancel_keyboard(f"account_{acc_id}"), parse_mode="Markdown")
    await callback.answer()

@router.message(UploadSingleState.waiting_for_video, F.video | F.document)
async def process_single_video(message: Message, state: FSMContext):
    file_id = message.video.file_id if message.video else message.document.file_id
    file_info = await message.bot.get_file(file_id)
    
    # Save local file
    file_ext = os.path.splitext(file_info.file_path or "video.mp4")[1] or ".mp4"
    saved_path = MEDIA_DIR / f"video_{message.from_user.id}_{int(asyncio.get_event_loop().time())}{file_ext}"
    
    await message.bot.download_file(file_info.file_path, destination=saved_path)
    await state.update_data(video_path=str(saved_path))
    
    # If video already had caption in Telegram, we can prefill
    caption = message.caption or ""
    if caption:
        await state.update_data(description=caption)
    
    await state.set_state(UploadSingleState.waiting_for_description)
    
    text = (
        "✅ Видео принято!\n\n"
        "Шаг 2/3: **Добавьте описание для видео**\n"
        "_(Отправьте текст описания, либо отправьте знак `-` или `пропустить`, чтобы оставить пустым)_:"
    )
    data = await state.get_data()
    acc_id = data["account_id"]
    await message.answer(text, reply_markup=get_cancel_keyboard(f"account_{acc_id}"), parse_mode="Markdown")

@router.message(UploadSingleState.waiting_for_description)
async def process_single_description(message: Message, state: FSMContext):
    desc = message.text.strip()
    if desc.lower() in ["-", "пропустить", "нет"]:
        desc = ""
    await state.update_data(description=desc)
    await state.set_state(UploadSingleState.waiting_for_hashtags)
    
    data = await state.get_data()
    acc_id = data["account_id"]
    
    text = (
        "✅ Описание сохранено!\n\n"
        "Шаг 3/3: **Добавьте хештеги** (например: `#fyp #viral #рек`)\n"
        "_(Либо отправьте `-` или `пропустить`)_:"
    )
    await message.answer(text, reply_markup=get_cancel_keyboard(f"account_{acc_id}"), parse_mode="Markdown")

@router.message(UploadSingleState.waiting_for_hashtags)
async def process_single_hashtags(message: Message, state: FSMContext):
    tags = message.text.strip()
    if tags.lower() in ["-", "пропустить", "нет"]:
        tags = ""
    await state.update_data(hashtags=tags)
    await state.set_state(UploadSingleState.confirm_upload)
    
    data = await state.get_data()
    acc_id = data["account_id"]
    acc = await db.get_account_by_id(acc_id)
    
    text = (
        "📋 **Подтверждение публикации:**\n\n"
        f"📱 Аккаунт: **{acc.get('name')}**\n"
        f"📝 Описание: {data.get('description') or '_(Без описания)_'}\n"
        f"🏷 Хештеги: `{data.get('hashtags') or 'Без хештегов'}`\n\n"
        "Нажмите **«Выложить»**, чтобы запустить загрузку в TikTok:"
    )
    await message.answer(text, reply_markup=get_confirm_upload_keyboard(acc_id), parse_mode="Markdown")

@router.callback_query(F.data.startswith("confirm_post_"))
async def execute_single_post(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    acc_id = int(callback.data.split("_")[2])
    acc = await db.get_account_by_id(acc_id)
    
    video_path = data.get("video_path")
    description = data.get("description", "")
    hashtags = data.get("hashtags", "")
    
    await state.clear()
    
    status_msg = await callback.message.edit_text(
        f"⏳ **Публикация в {acc.get('name')}...**\n"
        "Запускаю эмуляцию и передаю видео в TikTok Creator Portal. Это займет 20–40 секунд...",
        parse_mode="Markdown"
    )
    
    success, msg = await TikTokService.upload_video(
        cookies_json=acc["cookies_json"],
        video_path=video_path,
        description=description,
        hashtags=hashtags,
        proxy_str=acc.get("proxy", "")
    )
    if video_path:
        try:
            Path(video_path).unlink(missing_ok=True)
        except OSError:
            pass
    if success:
        await db.save_account_video(
            account_id=acc_id,
            tiktok_video_id="",
            title=(description or "")[:500],
            views=0,
            likes=0,
            comments=0,
            video_url=""
        )
    
    if success:
        result_text = (
            f"🎉 **Видео успешно опубликовано в аккаунт {acc.get('name')}!**\n\n"
            f"📝 Описание: {description}\n"
            f"🏷 Хештеги: {hashtags}"
        )
    else:
        result_text = (
            f"❌ **Не удалось опубликовать в {acc.get('name')}**\n\n"
            f"Причина: `{msg}`\n\n"
            "Проверьте валидность прокси и cookies аккаунта."
        )
        
    await status_msg.edit_text(result_text, reply_markup=get_account_menu_keyboard(acc_id), parse_mode="Markdown")
    await callback.answer()


# ==================== МАССОВАЯ ЗАГРУЗКА ВО ВСЕ АККАУНТЫ ====================

@router.callback_query(F.data == "upload_to_all")
async def upload_all_start(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(UploadAllState.waiting_for_video)
    
    accounts = await db.get_all_accounts()
    if not accounts:
        await callback.answer("❌ Сначала добавьте хотя бы 1 аккаунт!", show_alert=True)
        return
        
    text = (
        "🚀 **Массовая публикация во ВСЕ аккаунты**\n\n"
        f"Всего аккаунтов для залива: **{len(accounts)}**\n\n"
        "Шаг 1/3: **Отправьте видео файл**, который будет разослан во все профили:"
    )
    await callback.message.edit_text(text, reply_markup=get_cancel_keyboard("back_to_main"), parse_mode="Markdown")
    await callback.answer()

@router.message(UploadAllState.waiting_for_video, F.video | F.document)
async def process_all_video(message: Message, state: FSMContext):
    file_id = message.video.file_id if message.video else message.document.file_id
    file_info = await message.bot.get_file(file_id)
    
    file_ext = os.path.splitext(file_info.file_path or "video.mp4")[1] or ".mp4"
    saved_path = MEDIA_DIR / f"mass_video_{message.from_user.id}_{int(asyncio.get_event_loop().time())}{file_ext}"
    
    await message.bot.download_file(file_info.file_path, destination=saved_path)
    await state.update_data(video_path=str(saved_path))
    
    if message.caption:
        await state.update_data(description=message.caption)
        
    await state.set_state(UploadAllState.waiting_for_description)
    
    text = (
        "✅ Видео сохранено!\n\n"
        "Шаг 2/3: **Добавьте общее описание** (или отправьте `-` для пропуска):"
    )
    await message.answer(text, reply_markup=get_cancel_keyboard("back_to_main"), parse_mode="Markdown")

@router.message(UploadAllState.waiting_for_description)
async def process_all_description(message: Message, state: FSMContext):
    desc = message.text.strip()
    if desc.lower() in ["-", "пропустить", "нет"]:
        desc = ""
    await state.update_data(description=desc)
    await state.set_state(UploadAllState.waiting_for_hashtags)
    
    text = (
        "✅ Описание сохранено!\n\n"
        "Шаг 3/3: **Добавьте хештеги** (или отправьте `-` для пропуска):"
    )
    await message.answer(text, reply_markup=get_cancel_keyboard("back_to_main"), parse_mode="Markdown")

@router.message(UploadAllState.waiting_for_hashtags)
async def process_all_hashtags(message: Message, state: FSMContext):
    tags = message.text.strip()
    if tags.lower() in ["-", "пропустить", "нет"]:
        tags = ""
    await state.update_data(hashtags=tags)
    await state.set_state(UploadAllState.confirm_upload)
    
    accounts = await db.get_all_accounts()
    data = await state.get_data()
    
    text = (
        "🚀 **Подтверждение массовой публикации:**\n\n"
        f"Будет опубликовано на: **{len(accounts)} аккаунтов**\n"
        f"📝 Описание: {data.get('description') or '_(Без описания)_'}\n"
        f"🏷 Хештеги: `{data.get('hashtags') or 'Без хештегов'}`\n\n"
        "⚠️ _Публикация будет происходить по очереди с паузами, чтобы избежать блокировок._\n\n"
        "Нажмите **«Выложить во все сразу»** для старта:"
    )
    await message.answer(text, reply_markup=get_confirm_mass_upload_keyboard(), parse_mode="Markdown")

@router.callback_query(F.data == "confirm_mass_post")
async def execute_mass_post(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    video_path = data.get("video_path")
    description = data.get("description", "")
    hashtags = data.get("hashtags", "")
    
    await state.clear()
    accounts = await db.get_all_accounts()
    total = len(accounts)
    
    status_msg = await callback.message.edit_text(
        f"⏳ **Запуск очереди публикации на {total} аккаунтов...**",
        parse_mode="Markdown"
    )
    
    success_count = 0
    fail_count = 0
    logs = []
    
    for idx, acc in enumerate(accounts, 1):
        acc_name = acc.get("name") or f"Акк {acc['id']}"
        await status_msg.edit_text(
            f"🔄 **Публикация {idx}/{total}: {acc_name}...**\n"
            f"Успешно: {success_count} | Ошибок: {fail_count}",
            parse_mode="Markdown"
        )
        
        success, msg = await TikTokService.upload_video(
            cookies_json=acc["cookies_json"],
            video_path=video_path,
            description=description,
            hashtags=hashtags,
            proxy_str=acc.get("proxy", "")
        )
        if success:
            await db.save_account_video(
                account_id=acc["id"], tiktok_video_id="",
                title=(description or "")[:500], views=0, likes=0, comments=0, video_url=""
            )
            success_count += 1
            logs.append(f"✅ {acc_name}: Опубликовано")
        else:
            fail_count += 1
            logs.append(f"❌ {acc_name}: {msg}")
            
        # Small delay between uploads
        if idx < total:
            await asyncio.sleep(10)
            
    try:
        Path(video_path).unlink(missing_ok=True)
    except OSError:
        pass
    summary = (
        f"🏁 **Массовая публикация завершена!**\n\n"
        f"Итог: {success_count} из {total} успешно.\n\n"
        + "\n".join(logs)
    )
    await status_msg.edit_text(summary, reply_markup=get_main_menu_keyboard(accounts), parse_mode="Markdown")
    await callback.answer()
