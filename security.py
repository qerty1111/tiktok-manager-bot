from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery
from config import ADMIN_IDS

class IsAuthorized(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        # Configure ADMIN_IDS in .env for production. Empty keeps the existing single-user setup usable.
        return not ADMIN_IDS or (event.from_user is not None and event.from_user.id in ADMIN_IDS)
