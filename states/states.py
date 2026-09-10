from aiogram.fsm.state import State, StatesGroup

class AddAccountState(StatesGroup):
    waiting_for_name = State()
    waiting_for_cookies = State()
    waiting_for_proxy = State()

class UploadSingleState(StatesGroup):
    waiting_for_video = State()
    waiting_for_description = State()
    waiting_for_hashtags = State()
    confirm_upload = State()

class UploadAllState(StatesGroup):
    waiting_for_video = State()
    waiting_for_description = State()
    waiting_for_hashtags = State()
    confirm_upload = State()

class EditProfileState(StatesGroup):
    waiting_for_bio = State()
    waiting_for_photo = State()

class InteractionState(StatesGroup):
    waiting_for_account = State()
    waiting_for_url = State()
    waiting_for_action = State()
    waiting_for_comment = State()

