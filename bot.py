import os
import json
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
import tempfile
import os
import speech_recognition as sr
from pydub import AudioSegment
import asyncio
import config
from sheets import SheetsClient
from crm import CRMClient
import gamification

# Global references that will be set on startup
sheets_client = None
crm_client = None
team_client = None

# Track user state
# pending_location_requests: dict of user_id -> datetime (when requested)
# pending_plan_requests: dict of user_id -> list of task dicts (to match response)
pending_location_requests = {}
pending_plan_requests = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for private chat /start command."""
    user = update.effective_user
    chat_type = update.effective_chat.type
    
    if chat_type != "private":
        await update.message.reply_text("Пожалуйста, запустите меня в личных сообщениях.")
        return

    username = user.username or ""
    user_id = str(user.id)
    
    await update.message.reply_text(
        f"Привет, {user.first_name}! Я бот контроля рабочего времени.\n"
        f"Твой Telegram ID: `{user_id}`\n"
        f"Твой Username: `@{username}`\n\n"
        "Выполняю поиск твоего профиля в Google Таблице...",
        parse_mode="Markdown"
    )

    # Attempt to automatically link user ID by matching Telegram Username
    success, emp_name = try_register_user(username, user_id)
    if success:
        keyboard = [[KeyboardButton("📍 Отправить геопозицию для чекина", request_location=True)]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
        
        await update.message.reply_text(
            f"🎉 Успешно! Твой профиль сопоставлен с сотрудником **{emp_name}**.\n"
            "Telegram ID записан в Google Таблицу.\n\n"
            "Чтобы отметиться о начале рабочего дня, нажми на кнопку ниже или отправь геопозицию.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    else:
        # If not found automatically, offer inline keyboard
        employees = sheets_client.get_employees()
        unlinked = [e.get("ФИО") for e in employees if not str(e.get("Telegram User ID", "")).strip()]
        
        if unlinked:
            keyboard = []
            for name in unlinked:
                keyboard.append([InlineKeyboardButton(name, callback_data=f"reg_{name}")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"⚠️ Я не смог найти профиль `@{username}` автоматически.\n\n"
                "Пожалуйста, выбери свое имя из списка сотрудников ниже:",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"⚠️ Я не нашел имя пользователя `@{username}` в Google Таблице, и свободных профилей больше нет.\n\n"
                "Пожалуйста, попросите администратора добавить вас.",
                parse_mode="Markdown"
            )

async def handle_register_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles inline keyboard registration."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data.startswith("reg_"):
        emp_name = data[4:]
        user_id = str(query.from_user.id)
        
        sheets_client.update_employee_field(emp_name, "Telegram User ID", user_id)
        
        keyboard = [[KeyboardButton("📍 Отправить геопозицию для чекина", request_location=True)]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
        
        await query.edit_message_text(f"🎉 Успешно! Твой профиль сопоставлен с сотрудником **{emp_name}**.", parse_mode="Markdown")
        await query.message.reply_text("Чтобы отметиться о начале рабочего дня, нажми на кнопку ниже или отправь геопозицию.", reply_markup=reply_markup)

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually link employee name to Telegram ID."""
    user = update.effective_user
    chat_type = update.effective_chat.type
    
    if chat_type != "private":
        return

    if not context.args:
        await update.message.reply_text("Пожалуйста, укажите ФИО. Пример: `/register Александр Кузнецов`", parse_mode="Markdown")
        return

    target_name = " ".join(context.args).strip()
    user_id = str(user.id)
    
    employees = sheets_client.get_employees()
    found = False
    for emp in employees:
        if emp.get("ФИО", "").lower() == target_name.lower():
            found = True
            break
            
    if found:
        sheets_client.update_employee_field(target_name, "Telegram User ID", user_id)
        # Also update username if available
        if user.username:
            sheets_client.update_employee_field(target_name, "Telegram Username", user.username)
            
        keyboard = [[KeyboardButton("📍 Отправить геопозицию для чекина", request_location=True)]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
        
        await update.message.reply_text(
            f"🎉 Успешно! Telegram ID зарегистрирован для сотрудника **{target_name}**.\n\n"
            "Для отметки используйте кнопку отправки геопозиции.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            f"❌ Сотрудник '{target_name}' не найден в Google Таблице.\n"
            "Проверьте правильность написания ФИО (как в таблице)."
        )

async def set_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sets the active group chat ID for reports."""
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("Эту команду нужно вызывать в группе Telegram!")
        return

    # Check if user is admin
    member = await chat.get_member(user.id)
    if member.status not in ["creator", "administrator"] and user.id != 162: # Allow IT director Alexandre bypass
        await update.message.reply_text("Только администраторы могут настраивать группу бота!")
        return

    # Save group ID
    state = config.load_state()
    state["group_chat_id"] = chat.id
    state["group_title"] = chat.title
    config.save_state(state)

    await update.message.reply_text(
        f"📢 Группа **{chat.title}** (ID: `{chat.id}`) успешно назначена как основной канал отчетов 'Красавчики'!",
        parse_mode="Markdown"
    )

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for location messages sent in private chat."""
    user = update.effective_user
    message = update.message
    
    if message.chat.type != "private":
        return

    user_id = str(user.id)
    location = message.location
    if not location and message.venue:
        location = message.venue.location
        
    if not location:
        return
    
    # 1. Find employee by TG User ID
    emp = find_employee_by_tg_id(user_id)
    if not emp:
        await message.reply_text(
            "⚠️ Вы не зарегистрированы в системе.\n"
            "Запустите команду `/start` или обратитесь к администратору."
        )
        return

    emp_name = emp.get("ФИО")
    
    is_controlled = str(emp.get("Контролировать", "да")).strip().lower() != "нет"
    if not is_controlled:
        await message.reply_text("Ваша посещаемость не контролируется ботом. Хорошего дня! 😊")
        return
    
    # 2. Check if already checked in today
    today_str = datetime.now().strftime("%Y-%m-%d")
    checkins = sheets_client.get_checkins_for_date(today_str)
    already_checked = any(c.get("ФИО") == emp_name for c in checkins)
    
    if already_checked:
        await message.reply_text("✅ Вы уже отмечались сегодня! Хорошего продолжения дня. 👍")
        return

    # 3. Calculate punctuality
    now_dt = datetime.now()
    now_time = now_dt.time()
    expected_start_str = sheets_client.get_employee_start_time(emp, now_dt)
    
    # Ensure seconds are present
    if len(expected_start_str.split(":")) == 2:
        expected_start_str += ":00"
        
    try:
        expected_start_time = datetime.strptime(expected_start_str, "%H:%M:%S").time()
    except Exception:
        expected_start_time = datetime.strptime("09:00:00", "%H:%M:%S").time()

    is_late = now_time > expected_start_time
    status = "Опоздал" if is_late else "Вовремя"
    
    # Format coordinates and map link
    coords = f"{location.latitude},{location.longitude}"
    map_link = f"https://www.google.com/maps?q={location.latitude},{location.longitude}"
    time_str = datetime.now().strftime("%H:%M:%S")

    # 4. Log to Google Sheets
    sheets_client.log_checkin(
        date_str=today_str,
        name=emp_name,
        time_str=time_str,
        checkin_type="TG Geoposition",
        status=status,
        coordinates=coords,
        map_link=map_link
    )

    # 5. Notify the employee
    if is_late:
        await message.reply_text(
            f"📍 Твоя геопозиция принята.\n"
            f"Время отметки: **{time_str}**.\n"
            f"🔴 Зафиксировано опоздание (ожидалось: {expected_start_str[:-3]}). Пожалуйста, приступай к работе!",
            parse_mode="Markdown"
        )
    else:
        await message.reply_text(
            f"📍 Твоя геопозиция принята.\n"
            f"Время отметки: **{time_str}**.\n"
            f"🟢 Ты отметился вовремя! Отличной работы сегодня! 👍",
            parse_mode="Markdown"
        )

    # Remove location request flag
    pending_location_requests.pop(user_id, None)

    # 6. Post notification in "Красавчики" group
    state = config.load_state()
    group_chat_id = state.get("group_chat_id")
    
    if group_chat_id:
        if is_late:
            msg = (
                f"🔴 **[Опоздание]**\n"
                f"**{emp_name}** отметился с опозданием.\n"
                f"🕒 Время старта: **{time_str}** (ожидалось: {expected_start_str[:-3]})\n"
                f"📍 Геопозиция: [Google Maps]({map_link})"
            )
            
            # Post lateness to Team portal
            croco_id = str(emp.get("Croco ID", "")).strip()
            if team_client and croco_id:
                team_client.mark_lateness(croco_id, today_str)
                
            # Streak evaluation
            new_streak, achievement_msg = gamification.process_morning_streak(sheets_client, emp_name, emp, is_late=True)
            if new_streak == 0 and int(emp.get("Дней подряд", 0) or 0) > 0:
                curr_streak = int(emp.get("Дней подряд", 0) or 0)
                msg += f"\n\n💔 Стрик без опозданий ({curr_streak} дн.) сброшен."
        else:
            new_streak, achievement_msg = gamification.process_morning_streak(sheets_client, emp_name, emp, is_late=False)
            msg = (
                f"🟢 **[Вовремя]**\n"
                f"**{emp_name}** отметился вовремя!\n"
                f"🕒 Время старта: **{time_str}**\n"
                f"🔥 Текущий стрик: **{new_streak} дн.**\n"
                f"📍 Геопозиция: [Google Maps]({map_link})"
            )
            # Post 8 hours to Team portal
            croco_id = str(emp.get("Croco ID", "")).strip()
            if team_client and croco_id:
                team_client.set_work_hours(croco_id, today_str, worked_time=8)
        try:
            await context.bot.send_message(chat_id=group_chat_id, text=msg, parse_mode="Markdown", disable_web_page_preview=True)
            if not is_late and achievement_msg:
                await context.bot.send_message(chat_id=group_chat_id, text=achievement_msg, parse_mode="Markdown")
        except Exception as e:
            print(f"[Bot] Failed to send group check-in notification: {e}")
    else:
        print("[Bot] Group chat ID not set. Skipping group notification.")

async def transcribe_voice(voice_file_path):
    wav_path = voice_file_path + ".wav"
    audio = AudioSegment.from_ogg(voice_file_path)
    audio.export(wav_path, format="wav")
    
    recognizer = sr.Recognizer()
    with sr.AudioFile(wav_path) as source:
        audio_data = recognizer.record(source)
        try:
            # Use Google Web Speech API (free, no key needed)
            text = recognizer.recognize_google(audio_data, language="ru-RU")
            return text
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as e:
            print(f"[Bot] Could not request results from Google Speech Recognition service; {e}")
            return ""
        finally:
            try:
                os.remove(wav_path)
            except Exception:
                pass

async def process_plan_submission(update, context, emp, text, voice_file_id=None):
    user_id = str(update.effective_user.id)
    emp_name = emp.get("ФИО")
    today_str = datetime.now().strftime("%Y-%m-%d")

    state = config.load_state()
    submitted_plans = state.setdefault("submitted_plans", {})
    
    # Clean up old dates to keep bot_state.json small
    for k in list(submitted_plans.keys()):
        if k != today_str:
            submitted_plans.pop(k, None)
            
    today_submitted = submitted_plans.setdefault(today_str, [])

    if str(emp.get("Запрашивать план", "")).strip().lower() != "да":
        checkins = sheets_client.get_checkins_for_date(today_str)
        already_checked = any(c.get("ФИО") == emp_name for c in checkins)
        if not already_checked:
            if str(emp.get("Есть CrocoTime", "")).strip().lower() == "да":
                await update.message.reply_text("Привет! У вас не запрашивается план на день.\nДля отметки о начале дня, пожалуйста, запустите CrocoTime.")
            else:
                await update.message.reply_text("Привет! У вас не запрашивается план на день.\nДля отметки о начале дня, пожалуйста, отправьте геопозицию.")
        return

    # If already submitted plan today, ignore further messages
    if emp_name in today_submitted:
        return

    # Log task plan to Sheets
    sheets_client.log_task_plan(today_str, emp_name, text)
    
    # Update submitted plans state
    today_submitted.append(emp_name)
    config.save_state(state)
    
    # Step 2: Request geolocation if needed
    needs_geo = (str(emp.get("Есть CrocoTime", "")).strip().lower() != "да")
    if needs_geo:
        keyboard = [[KeyboardButton("📍 Отправить геопозицию для чекина", request_location=True)]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(
            "📝 Твой план на день сохранен. Спасибо!\n\n"
            "📍 Если ты еще не отметил начало рабочего дня, не забудь отправить геопозицию (нажми кнопку ниже).",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text("📝 Твой план на день сохранен. Отличного рабочего дня! 👍")

    # Forward plan and audio to Admin
    admin_chat_id = "226959621"
    msg_to_admin = f"👤 **План от сотрудника {emp_name}:**\n\n{text if text else '<Без текста>'}"
    
    try:
        await context.bot.send_message(chat_id=admin_chat_id, text=msg_to_admin, parse_mode="Markdown")
        if voice_file_id:
            await context.bot.send_voice(chat_id=admin_chat_id, voice=voice_file_id)
    except Exception as e:
        print(f"[Bot] Failed to forward plan to admin: {e}")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for text responses to task plan/status requests."""
    user = update.effective_user
    message = update.message
    
    if message.chat.type != "private":
        return

    user_id = str(user.id)
    text = message.text.strip()
    
    emp = find_employee_by_tg_id(user_id)
    if not emp:
        return

    await process_plan_submission(update, context, emp, text)

async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for voice message responses to task plan requests."""
    user = update.effective_user
    message = update.message
    
    if message.chat.type != "private":
        return

    user_id = str(user.id)
    emp = find_employee_by_tg_id(user_id)
    if not emp:
        return

    # Only process if they actually need to submit a plan and haven't yet
    today_str = datetime.now().strftime("%Y-%m-%d")
    state = config.load_state()
    today_submitted = state.get("submitted_plans", {}).get(today_str, [])
    if str(emp.get("Запрашивать план", "")).strip().lower() != "да" or emp.get("ФИО") in today_submitted:
        return

    status_msg = await message.reply_text("⏳ Расшифровываю голосовое сообщение...")
    
    try:
        voice_file = await context.bot.get_file(message.voice.file_id)
        fd, temp_ogg = tempfile.mkstemp(suffix=".ogg")
        os.close(fd)
        
        await voice_file.download_to_drive(temp_ogg)
        
        # Run transcription in a separate thread so it doesn't block the async loop
        text = await asyncio.to_thread(transcribe_voice, temp_ogg)
        text = await text if asyncio.iscoroutine(text) else text
        
        try:
            os.remove(temp_ogg)
        except Exception:
            pass
            
        if not text:
            await status_msg.edit_text("❌ Не удалось распознать голос. Пожалуйста, напишите план текстом или запишите голосовое сообщение более четко.")
            return
            
        await status_msg.edit_text(f"✅ **Распознанный текст:**\n_{text}_\n\nСохраняю план...", parse_mode="Markdown")
        await process_plan_submission(update, context, emp, text, voice_file_id=message.voice.file_id)
        
    except Exception as e:
        print(f"[Bot] Error processing voice: {e}")
        await status_msg.edit_text("❌ Произошла ошибка при обработке голосового сообщения. Пожалуйста, напишите ваш план текстом.")

# Helper Functions
def try_register_user(tg_username, tg_user_id):
    """Matches username in sheets and saves user ID."""
    if not tg_username:
        return False, None
        
    employees = sheets_client.get_employees()
    for emp in employees:
        sheet_username = str(emp.get("Telegram Username", "")).strip().replace("@", "")
        if sheet_username.lower() == tg_username.lower():
            emp_name = emp.get("ФИО")
            sheets_client.update_employee_field(emp_name, "Telegram User ID", tg_user_id)
            return True, emp_name
            
    return False, None

def find_employee_by_tg_id(tg_user_id):
    """Lookup employee row by TG user ID."""
    employees = sheets_client.get_employees()
    for emp in employees:
        if str(emp.get("Telegram User ID", "")).strip() == tg_user_id:
            return emp
    return None

async def sync_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Syncs current group administrators to the Google Sheet."""
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("Эту команду нужно вызывать в группе Telegram!")
        return
        
    # Check if user is admin
    member = await chat.get_member(user.id)
    if member.status not in ["creator", "administrator"] and user.id != 162:
        await update.message.reply_text("Только администраторы могут запускать синхронизацию!")
        return
        
    # Save group ID dynamically
    state = config.load_state()
    if state.get("group_chat_id") != chat.id:
        state["group_chat_id"] = chat.id
        state["group_title"] = chat.title
        config.save_state(state)
        
    await update.message.reply_text("🔄 Синхронизирую участников группы с Google Таблицей...")
    
    try:
        admins = await chat.get_administrators()
        added_count = 0
        updated_count = 0
        
        for admin_member in admins:
            admin_user = admin_member.user
            if admin_user.is_bot:
                continue
                
            username = admin_user.username or ""
            first_name = admin_user.first_name or ""
            last_name = admin_user.last_name or ""
            name = f"{first_name} {last_name}".strip() or username or str(admin_user.id)
            user_id = str(admin_user.id)
            
            inserted = sheets_client.add_or_update_employee(name, username, user_id)
            if inserted:
                added_count += 1
            else:
                updated_count += 1
                
        await update.message.reply_text(
            f"✅ Синхронизация администраторов завершена!\n"
            f"Добавлено новых в таблицу: {added_count}\n"
            f"Обновлено существующих: {updated_count}\n\n"
            f"💡 Обычные участники будут автоматически добавляться/обновляться в таблице, когда они отправят любое сообщение в эту группу, либо при входе новых участников."
        )
    except Exception as e:
        print(f"[Bot] Failed to sync administrators: {e}")
        await update.message.reply_text(f"❌ Ошибка синхронизации: {e}")

async def chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle users joining or leaving the group chat."""
    chat_member_update = update.chat_member
    if not chat_member_update:
        return
        
    chat = chat_member_update.chat
    
    # Check if this update belongs to our registered group chat
    state = config.load_state()
    group_chat_id = state.get("group_chat_id")
    if not group_chat_id or chat.id != group_chat_id:
        return
        
    old_status = chat_member_update.old_chat_member.status
    new_status = chat_member_update.new_chat_member.status
    user = chat_member_update.new_chat_member.user
    
    if user.is_bot:
        return
        
    username = user.username or ""
    first_name = user.first_name or ""
    last_name = user.last_name or ""
    name = f"{first_name} {last_name}".strip() or username or str(user.id)
    user_id = str(user.id)
    
    joined_statuses = ["member", "administrator", "creator"]
    left_statuses = ["left", "kicked"]
    
    if old_status not in joined_statuses and new_status in joined_statuses:
        # Joined
        sheets_client.add_or_update_employee(name, username, user_id)
        print(f"[Bot] Auto-added new group member '{name}' on join.")
    elif old_status in joined_statuses and new_status in left_statuses:
        # Left
        sheets_client.remove_employee(username=username, user_id=user_id)
        print(f"[Bot] Auto-removed group member '{name}' on leave.")

async def group_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Auto-registers or updates users in the sheet when they send a message in the group."""
    user = update.effective_user
    chat = update.effective_chat
    
    if not user or user.is_bot:
        return
        
    # Ensure this is the registered group chat
    state = config.load_state()
    group_chat_id = state.get("group_chat_id")
    if not group_chat_id or chat.id != group_chat_id:
        return
        
    username = user.username or ""
    first_name = user.first_name or ""
    last_name = user.last_name or ""
    name = f"{first_name} {last_name}".strip() or username or str(user.id)
    user_id = str(user.id)
    
    # Perform silent add/update in Sheets
    sheets_client.add_or_update_employee(name, username, user_id)
