from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict, Any

def get_main_menu_keyboard(accounts: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    buttons = []
    # Dynamic list of accounts
    for acc in accounts:
        display_name = acc.get("name") or f"Аккаунт {acc['id']}"
        status_icon = "🟢" if acc.get("is_active") else "🔴"
        buttons.append([
            InlineKeyboardButton(
                text=f"{status_icon} {display_name}",
                callback_data=f"account_{acc['id']}"
            )
        ])
    
    # Global action buttons
    bottom_buttons = []
    if accounts:
        bottom_buttons.append([
            InlineKeyboardButton(text="🚀 Выложить во все аккаунты", callback_data="upload_to_all")
        ])
        bottom_buttons.append([
            InlineKeyboardButton(text="❤️ Лайки и 💬 Комментарии", callback_data="mass_interaction")
        ])
    bottom_buttons.append([
        InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data="add_account")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons + bottom_buttons)

def get_account_menu_keyboard(account_id: int) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(text="✏️ Изменить профиль", callback_data=f"edit_profile_{account_id}")
        ],
        [
            InlineKeyboardButton(text="🎬 Добавить видео", callback_data=f"upload_single_{account_id}")
        ],
        [
            InlineKeyboardButton(text="❤️ Лайк / 💬 Комментарий", callback_data=f"interact_{account_id}")
        ],
        [
            InlineKeyboardButton(text="📁 Все видео", callback_data=f"all_videos_{account_id}")
        ],
        [
            InlineKeyboardButton(text="❌ Удалить аккаунт", callback_data=f"delete_acc_{account_id}"),
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_interaction_action_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(text="❤️ Поставить лайк", callback_data="action_like")
        ],
        [
            InlineKeyboardButton(text="💬 Оставить комментарий", callback_data="action_comment")
        ],
        [
            InlineKeyboardButton(text="🔥 Лайк + Комментарий", callback_data="action_both")
        ],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_main")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_interaction_account_choice_keyboard(accounts: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    buttons = []
    if len(accounts) > 1:
        buttons.append([
            InlineKeyboardButton(text="🚀 Со ВСЕХ аккаунтов сразу", callback_data="target_acc_all")
        ])
    for acc in accounts:
        display_name = acc.get("name") or f"Аккаунт {acc['id']}"
        buttons.append([
            InlineKeyboardButton(text=f"👤 {display_name}", callback_data=f"target_acc_{acc['id']}")
        ])
    buttons.append([
        InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_main")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_profile_edit_keyboard(account_id: int) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(text="📝 Изменить описание", callback_data=f"change_bio_{account_id}")
        ],
        [
            InlineKeyboardButton(text="🖼 Изменить фото", callback_data=f"change_photo_{account_id}")
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data=f"account_{account_id}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_confirm_upload_keyboard(account_id: int) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(text="🚀 Выложить", callback_data=f"confirm_post_{account_id}")
        ],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"account_{account_id}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_confirm_mass_upload_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(text="🚀 Выложить во все сразу", callback_data="confirm_mass_post")
        ],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_main")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_videos_list_keyboard(account_id: int, videos: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    buttons = []
    for idx, v in enumerate(videos, 1):
        views = v.get("views_count", 0)
        likes = v.get("likes_count", 0)
        btn_text = f"🎥 Видео {idx} (👁 {views} | ❤️ {likes})"
        buttons.append([
            InlineKeyboardButton(text=btn_text, callback_data=f"view_video_{v['id']}")
        ])
    
    buttons.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data=f"account_{account_id}")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_video_detail_keyboard(account_id: int, video_url: str = "") -> InlineKeyboardMarkup:
    buttons = []
    if video_url:
        buttons.append([
            InlineKeyboardButton(text="🔗 Открыть в TikTok", url=video_url)
        ])
    buttons.append([
        InlineKeyboardButton(text="⬅️ Назад к списку видео", callback_data=f"all_videos_{account_id}")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_cancel_keyboard(callback_back: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data=callback_back)]]
    )
