import os
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from security import IsAuthorized

from database import db
from config import MEDIA_DIR
from keyboards.keyboards import (
    get_profile_edit_keyboard,
    get_cancel_keyboard,
    get_account_menu_keyboard,
    get_videos_list_keyboard,
    get_video_detail_keyboard
)
from states.states import EditProfileState
from services.tiktok_service import TikTokService

router = Router()
router.message.filter(IsAuthorized())
router.callback_query.filter(IsAuthorized())

# ==================== УПРАВЛЕНИЕ ПРОФИЛЕМ ====================

@router.callback_query(F.data.startswith("edit_profile_"))
async def edit_profile_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    acc_id = int(callback.data.split("_")[2])
    acc = await db.get_account_by_id(acc_id)
    
    text = (
        f"✏️ **Редактирование профиля: {acc.get('name')}**\n\n"
        "Выберите, что вы хотите изменить:"
    )
    await callback.message.edit_text(text, reply_markup=get_profile_edit_keyboard(acc_id), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("change_bio_"))
async def change_bio_start(callback: CallbackQuery, state: FSMContext):
    acc_id = int(callback.data.split("_")[2])
    await state.update_data(account_id=acc_id)
    await state.set_state(EditProfileState.waiting_for_bio)
    
    text = (
        "📝 **Изменение описания (Bio)**\n\n"
        "Отправьте новый текст био для аккаунта TikTok (до 80 символов):"
    )
    await callback.message.edit_text(text, reply_markup=get_cancel_keyboard(f"edit_profile_{acc_id}"), parse_mode="Markdown")
    await callback.answer()

@router.message(EditProfileState.waiting_for_bio)
async def process_new_bio(message: Message, state: FSMContext):
    new_bio = message.text.strip()
    data = await state.get_data()
    acc_id = data["account_id"]
    acc = await db.get_account_by_id(acc_id)
    await state.clear()
    
    msg = await message.answer("🔄 Применяю новое описание в TikTok профиле через браузер...")
    
    success, result_msg = await TikTokService.update_profile_bio(
        cookies_json=acc["cookies_json"],
        username=acc.get("username", ""),
        new_bio=new_bio,
        proxy_str=acc.get("proxy", "")
    )
    
    if success:
        await msg.edit_text(
            f"✅ **Описание успешно обновлено в TikTok!**\n\nНовое био: `{new_bio}`",
            reply_markup=get_account_menu_keyboard(acc_id),
            parse_mode="Markdown"
        )
    else:
        await msg.edit_text(
            f"❌ **Не удалось обновить био:**\n`{result_msg}`",
            reply_markup=get_account_menu_keyboard(acc_id),
            parse_mode="Markdown"
        )

@router.callback_query(F.data.startswith("change_photo_"))
async def change_photo_start(callback: CallbackQuery, state: FSMContext):
    acc_id = int(callback.data.split("_")[2])
    await state.update_data(account_id=acc_id)
    await state.set_state(EditProfileState.waiting_for_photo)
    
    text = (
        "🖼 **Изменение фото профиля (Аватар)**\n\n"
        "Отправьте новую фотографию в чат:"
    )
    await callback.message.edit_text(text, reply_markup=get_cancel_keyboard(f"edit_profile_{acc_id}"), parse_mode="Markdown")
    await callback.answer()

@router.message(EditProfileState.waiting_for_photo, F.photo)
async def process_new_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    acc_id = data["account_id"]
    acc = await db.get_account_by_id(acc_id)
    await state.clear()
    
    photo = message.photo[-1]
    file_info = await message.bot.get_file(photo.file_id)
    saved_path = MEDIA_DIR / f"avatar_{acc_id}.jpg"
    await message.bot.download_file(file_info.file_path, destination=saved_path)
    
    msg = await message.answer("🔄 Загружаю новую аватарку в TikTok через браузер... Подождите 15–25 секунд.")
    
    success, result_msg = await TikTokService.update_profile_avatar(
        cookies_json=acc["cookies_json"],
        username=acc.get("username", ""),
        photo_path=str(saved_path),
        proxy_str=acc.get("proxy", "")
    )
    
    if success:
        await msg.edit_text(
            "✅ **Аватарка успешно обновлена в профиле TikTok!**",
            reply_markup=get_account_menu_keyboard(acc_id),
            parse_mode="Markdown"
        )
    else:
        await msg.edit_text(
            f"❌ **Не удалось обновить аватарку:**\n`{result_msg}`",
            reply_markup=get_account_menu_keyboard(acc_id),
            parse_mode="Markdown"
        )


# ==================== ВСЕ ВИДЕО АККАУНТА ====================

@router.callback_query(F.data.startswith("all_videos_"))
async def all_videos_list(callback: CallbackQuery):
    acc_id = int(callback.data.split("_")[2])
    acc = await db.get_account_by_id(acc_id)
    videos = await db.get_account_videos(acc_id, limit=10)
    
    if not videos:
        text = (
            f"📁 **Все видео: {acc.get('name')}**\n\n"
            "У этого аккаунта пока нет сохраненных видео в боте.\n"
            "Вы можете загрузить видео через кнопку «🎬 Добавить видео»."
        )
    else:
        text = (
            f"📁 **Все видео: {acc.get('name')}**\n\n"
            "Нажмите на видео, чтобы посмотреть подробную статистику (просмотры, лайки):"
        )
        
    await callback.message.edit_text(text, reply_markup=get_videos_list_keyboard(acc_id, videos), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("view_video_"))
async def view_video_detail(callback: CallbackQuery):
    video_id = int(callback.data.split("_")[2])
    async with db.aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = db.aiosqlite.Row
        async with conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)) as cursor:
            v = await cursor.fetchone()
            
    if not v:
        await callback.answer("Видео не найдено", show_alert=True)
        return
        
    text = (
        f"🎬 **Видео #{v['id']}**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📝 Заголовок: {v['title'] or 'Без описания'}\n"
        f"👁 Просмотры: **{v['views_count']:,}**\n"
        f"❤️ Лайки: **{v['likes_count']:,}**\n"
        f"💬 Комментарии: **{v['comments_count']:,}**\n"
        f"━━━━━━━━━━━━━━━━━━━"
    )
    await callback.message.edit_text(text, reply_markup=get_video_detail_keyboard(v['account_id'], v.get("video_url", "")), parse_mode="Markdown")
    await callback.answer()
