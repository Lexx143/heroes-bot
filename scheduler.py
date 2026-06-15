import asyncio
from datetime import datetime, timedelta
from telegram import ReplyKeyboardMarkup, KeyboardButton
import config
from sheets import SheetsClient
import gamification

# Global client references set at startup
sheets_client = None
croco_client = None
crm_client = None
team_client = None

# Track last executed dates/minutes to prevent double-runs or missed runs
last_run_dates = {
    "location_request": None,
    "crm_request": None,
    "streak_check": None
}
last_croco_poll_minute = None

async def scheduler_loop(application):
    global last_croco_poll_minute
    print("[Scheduler] Loop started.")
    
    # Wait for the bot to be fully initialized
    await asyncio.sleep(10)
    
    while True:
        try:
            now = datetime.now()
            
            # Run jobs only on weekdays (Mon=0 to Fri=4)
            if now.weekday() < 5:
                today_str = now.strftime("%Y-%m-%d")
                
                # 1. Poll CrocoTime every 5 minutes between 08:00 and 11:00 AM
                if 8 <= now.hour < 11 and now.minute % 5 == 0 and last_croco_poll_minute != now.minute:
                    last_croco_poll_minute = now.minute
                    await poll_crocotime_work_start(application, today_str)
                
                # 2. Check and send individual morning plan/geoposition requests (runs every minute check)
                await check_and_send_morning_requests(application, today_str, now)
                
                # 4. Check Streaks & Achievements at 07:00 PM (19:00)
                if now.hour == 19 and now.minute == 0 and last_run_dates["streak_check"] != today_str:
                    last_run_dates["streak_check"] = today_str
                    await check_daily_streaks(application, today_str)
                    
            # 5. Broadcast reminder on Sunday at 19:00 for unstarted users
            if now.weekday() == 6 and now.hour == 19 and now.minute == 0 and last_run_dates.get("sunday_broadcast") != now.strftime("%Y-%m-%d"):
                last_run_dates["sunday_broadcast"] = now.strftime("%Y-%m-%d")
                await broadcast_unstarted_users(application)
                    
        except Exception as e:
            print(f"[Scheduler] Error in loop: {e}")
            
        # Check every 30 seconds to make sure we don't miss a minute boundary
        await asyncio.sleep(30)

async def poll_crocotime_work_start(application, today_str):
    print(f"[Scheduler] Polling CrocoTime for {today_str}...")
    
    # 1. Fetch work starts from CrocoTime
    starts = croco_client.get_work_start_times(today_str)
    if not starts:
        return

    # 2. Get registered employees
    employees = sheets_client.get_employees()
    checkins = sheets_client.get_checkins_for_date(today_str)
    checked_in_names = {c.get("ФИО") for c in checkins}
    
    state = config.load_state()
    group_chat_id = state.get("group_chat_id")

    for emp in employees:
        emp_name = emp.get("ФИО")
        croco_id = emp.get("Croco ID") # E.g., "IT116"
        
        if str(emp.get("Есть CrocoTime", "")).strip().lower() != "да" or not croco_id:
            continue
            
        # Check if we already logged a CrocoTime entry for this user today
        already_logged = False
        for c in checkins:
            if c.get("ФИО") == emp_name and c.get("Тип") == "CrocoTime":
                already_logged = True
                break
        
        if already_logged:
            continue

        # Look for matching employee record in CrocoTime starts
        # Match by Croco ID prefix in display name
        matched_start = None
        for display_name, start_data in starts.items():
            if display_name.startswith(croco_id) or croco_id in display_name:
                matched_start = start_data
                break
                
        if matched_start:
            time_str = matched_start["time_str"]
            work_begin_seconds = matched_start["seconds"]
            
            # Check individual expected start time
            expected_start_str = SheetsClient.get_employee_start_time(emp, datetime.now())
            if len(expected_start_str.split(":")) == 2:
                expected_start_str += ":00"
            
            try:
                expected_dt = datetime.strptime(expected_start_str, "%H:%M:%S")
                expected_seconds = expected_dt.hour * 3600 + expected_dt.minute * 60 + expected_dt.second
            except Exception:
                expected_seconds = 9 * 3600

            is_late = work_begin_seconds > expected_seconds
            status = "Опоздал" if is_late else "Вовремя"
            
            # Log to Sheets
            sheets_client.log_checkin(
                date_str=today_str,
                name=emp_name,
                time_str=time_str,
                checkin_type="CrocoTime",
                status=status
            )
            
            if team_client and is_late:
                team_client.mark_lateness(croco_id, today_str)
            
            print(f"[Scheduler] CrocoTime start logged for {emp_name}: {time_str} ({status})")
            
            # Post to group
            if group_chat_id:
                if is_late:
                    msg = (
                        f"🔴 **[Опоздание]**\n"
                        f"**{emp_name}** приступил к работе (CrocoTime).\n"
                        f"🕒 Время старта: **{time_str}** (ожидалось: {expected_start_str[:-3]})"
                    )
                    # Streak evaluation
                    new_streak, achievement_msg = gamification.process_morning_streak(sheets_client, emp_name, emp, is_late=True)
                    if new_streak == 0 and int(emp.get("Дней подряд", 0) or 0) > 0:
                        curr_streak = int(emp.get("Дней подряд", 0) or 0)
                        msg += f"\n\n💔 Стрик без опозданий ({curr_streak} дн.) сброшен."
                else:
                    new_streak, achievement_msg = gamification.process_morning_streak(sheets_client, emp_name, emp, is_late=False)
                    msg = (
                        f"🟢 **[Вовремя]**\n"
                        f"**{emp_name}** приступил к работе (CrocoTime).\n"
                        f"🕒 Время старта: **{time_str}**\n"
                        f"🔥 Текущий стрик: **{new_streak} дн.**"
                    )
                try:
                    await application.bot.send_message(chat_id=group_chat_id, text=msg)
                    if not is_late and achievement_msg:
                        await application.bot.send_message(chat_id=group_chat_id, text=achievement_msg, parse_mode="Markdown")
                except Exception as e:
                    print(f"[Scheduler] Failed to send CrocoTime announcement: {e}")

async def check_and_send_morning_requests(application, today_str, now):
    # Run from 5:00 AM to 23:00 PM
    if not (5 <= now.hour < 23):
        return
        
    state = config.load_state()
    sent_requests = state.setdefault("sent_morning_requests", {})
    sent_reminders = state.setdefault("sent_start_reminders", {})
    
    # Clean up old dates from state
    for k in list(sent_requests.keys()):
        if k != today_str:
            sent_requests.pop(k, None)
    for k in list(sent_reminders.keys()):
        if k != today_str:
            sent_reminders.pop(k, None)
            
    today_sent = sent_requests.setdefault(today_str, [])
    today_reminded = sent_reminders.setdefault(today_str, [])
    
    employees = sheets_client.get_employees()
    
    for emp in employees:
        emp_name = emp.get("ФИО")
        tg_user_id = emp.get("Telegram User ID")
        
        if not tg_user_id:
            continue
            
        if emp_name in today_sent:
            continue
            
        croco_id = str(emp.get("Croco ID", "")).strip()
        if team_client and croco_id:
            has_excuse = team_client.get_user_status_for_date(croco_id, today_str)
            if has_excuse:
                print(f"[Scheduler] Skipping morning request for {emp_name} due to Vacation/Sickday in Team portal.")
                continue
                
        wants_plan = (str(emp.get("Запрашивать план", "")).strip().lower() == "да")
        needs_geo = (str(emp.get("Есть CrocoTime", "")).strip().lower() != "да")
        
        if not wants_plan and not needs_geo:
            continue
            
        # Parse individual start time
        start_time_str = SheetsClient.get_employee_start_time(emp, now)
        try:
            start_dt = datetime.strptime(start_time_str, "%H:%M:%S")
        except Exception:
            start_dt = datetime.strptime("09:00:00", "%H:%M:%S")
            
        # Target request time: start_dt - 15 minutes
        target_time = (start_dt - timedelta(minutes=15)).time()
        
        current_time = now.time()
        
        if current_time >= target_time and emp_name not in today_sent:
            # 1. Check if user has started the bot using send_chat_action
            try:
                await application.bot.send_chat_action(chat_id=tg_user_id, action="typing")
            except Exception as e:
                err_str = str(e).lower()
                if "forbidden" in err_str or "peer_id_invalid" in err_str or "chat not found" in err_str:
                    if emp_name not in today_reminded:
                        # Send group reminder
                        group_chat_id = state.get("group_chat_id")
                        if group_chat_id:
                            username = emp.get("Telegram Username", "")
                            mention = f"@{username}" if username else emp_name
                            
                            bot_info = await application.bot.get_me()
                            bot_username = bot_info.username
                            
                            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                            keyboard = [[InlineKeyboardButton("🚀 Запустить бота", url=f"https://t.me/{bot_username}?start=1")]]
                            reply_markup = InlineKeyboardMarkup(keyboard)
                            
                            msg = f"⚠️ {mention}, скоро начало рабочего дня! Пожалуйста, запустите бота в личных сообщениях, чтобы я мог прислать ваши задачи из CRM."
                            try:
                                await application.bot.send_message(
                                    chat_id=group_chat_id, 
                                    text=msg,
                                    reply_markup=reply_markup
                                )
                            except Exception as inner_e:
                                print(f"[Scheduler] Failed to send group reminder: {inner_e}")
                        
                        today_reminded.append(emp_name)
                        config.save_state(state)
                # Skip to next employee, wait until they start the bot
                continue
                
            # 2. If we reach here, user has started the bot! Prepare and send the morning request.
            msg_parts = [f"Привет, {emp_name}! Через 10 минут начинается твой рабочий день."]
            reply_markup = None
            
            # Geoposition request (only if no plan is required, otherwise we ask AFTER the plan)
            if needs_geo and not wants_plan:
                msg_parts.append(
                    "📍 Пожалуйста, отправь свою геопозицию для чекина (нажми кнопку ниже)."
                )
                keyboard = [[KeyboardButton("📍 Отправить геопозицию для чекина", request_location=True)]]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
                
            # CRM plan request
            if wants_plan:
                crm_id = emp.get("CRM ID")
                tasks = None
                if crm_id:
                    try:
                        tasks = crm_client.get_active_tasks(crm_id)
                    except Exception as e:
                        print(f"[Scheduler] Failed to fetch CRM tasks for {emp_name}: {e}")
                
                if tasks:
                    task_list_str = ""
                    for idx, t in enumerate(tasks):
                        task_list_str += f"{idx+1}. [{t['subject']}]({t['url']}) (Статус: {t['status']})\n"
                    msg_parts.append(
                        f"📝 Сегодня на тебе висят следующие задачи в CRM:\n\n{task_list_str}\n"
                        "Пожалуйста, пришли в ответ краткий план / статус по ним на сегодня."
                    )
                else:
                    msg_parts.append(
                        "📝 На сегодня у тебя нет активных задач в CRM. Пожалуйста, напиши свой краткий план на день."
                    )
                    
            final_msg = "\n\n".join(msg_parts)
            
            try:
                await application.bot.send_message(
                    chat_id=tg_user_id,
                    text=final_msg,
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                    reply_markup=reply_markup
                )
                print(f"[Scheduler] Sent morning request to {emp_name} ({tg_user_id})")
                
                # Mark as sent
                today_sent.append(emp_name)
                config.save_state(state)
            except Exception as e:
                print(f"[Scheduler] Failed to send morning request to {emp_name}: {e}")

async def check_daily_streaks(application, today_str):
    print(f"[Scheduler] Calculating daily streaks for {today_str}...")
    employees = sheets_client.get_employees()
    checkins = sheets_client.get_checkins_for_date(today_str)
    
    # Map employee name to check-in record
    checkin_map = {c.get("ФИО"): c for c in checkins}
    
    state = config.load_state()
    group_chat_id = state.get("group_chat_id")

    for emp in employees:
        emp_name = emp.get("ФИО")
        curr_streak = int(emp.get("Дней подряд", 0) or 0)
        curr_ach = emp.get("Текущая ачивка", "")
        
        c_record = checkin_map.get(emp_name)
        
        # Determine status: "Вовремя", "Опоздал", "Отпуск", "Больничный", or None (absent)
        status = c_record.get("Статус") if c_record else None
        
        # Check Team Portal for valid excuses (vacation, sick day)
        croco_id = str(emp.get("Croco ID", "")).strip()
        if team_client and croco_id:
            if team_client.get_user_status_for_date(croco_id, today_str):
                status = "Уважительная"
        
        # Streak rules (Evening):
        # Morning logic already handles "Вовремя" (increments) and "Опоздал" (resets).
        # Here we only handle "Absent" (None) or "Уважительная"/"Отпуск"/"Больничный".
        if status in ["Отпуск", "Больничный", "Уважительная"]:
            print(f"[Scheduler] Streak frozen for {emp_name} (Status: {status})")
        elif status == "Вовремя" or status == "Опоздал":
            pass # Already handled in the morning
        else:
            # Absent (None) -> reset streak
            sheets_client.update_employee_field(emp_name, "Дней подряд", 0)
            if curr_streak > 0:
                sheets_client.update_employee_field(emp_name, "Текущая ачивка", "")
            if group_chat_id:
                msg = f"💔 **{emp_name}** опоздал или отсутствовал. Стрик без опозданий ({curr_streak} дн.) сброшен."
                try:
                    await application.bot.send_message(chat_id=group_chat_id, text=msg)
                except Exception as e:
                    print(f"[Scheduler] Failed to send streak reset notification: {e}")
                    
        print(f"[Scheduler] Daily streak calculated for {emp_name}: {curr_streak} -> {new_streak}")

async def broadcast_unstarted_users(application):
    print("[Scheduler] Running Sunday broadcast for unstarted users...")
    state = config.load_state()
    group_chat_id = state.get("group_chat_id")
    if not group_chat_id:
        return
        
    employees = sheets_client.get_employees()
    unstarted = []
    
    for emp in employees:
        emp_name = emp.get("ФИО", "Unknown")
        tg_user_id = emp.get("Telegram User ID")
        
        if not tg_user_id:
            # Didn't even join the group after the bot was added
            username = emp.get("Telegram Username", "")
            unstarted.append(f"@{username}" if username else emp_name)
            continue
            
        try:
            await application.bot.send_chat_action(chat_id=tg_user_id, action="typing")
        except Exception as e:
            err_str = str(e).lower()
            if "forbidden" in err_str or "peer_id_invalid" in err_str or "chat not found" in err_str:
                username = emp.get("Telegram Username", "")
                unstarted.append(f"@{username}" if username else emp_name)
                
    if unstarted:
        bot_info = await application.bot.get_me()
        bot_username = bot_info.username
        
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = [[InlineKeyboardButton("🚀 Запустить бота", url=f"https://t.me/{bot_username}?start=1")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        mentions = " ".join(unstarted)
        msg = f"⚠️ {mentions}\n\nКоллеги, напоминаю, что вам необходимо запустить меня в личных сообщениях до понедельника, чтобы я мог присылать вам задачи!\nПожалуйста, нажмите на кнопку ниже и отправьте /start"
        
        try:
            await application.bot.send_message(
                chat_id=group_chat_id, 
                text=msg,
                reply_markup=reply_markup
            )
        except Exception as e:
            print(f"[Scheduler] Failed to send Sunday broadcast: {e}")
