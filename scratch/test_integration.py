import os
import sys
import unittest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone

# Add the project root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
import croco
import crm
import sheets
import scheduler
import bot

class TestWorkdayBotIntegration(unittest.TestCase):
    def setUp(self):
        # Create mock clients
        self.mock_sheets = MagicMock()
        self.mock_croco = MagicMock()
        self.mock_crm = MagicMock()

        # Bind mock clients to scheduler
        scheduler.sheets_client = self.mock_sheets
        scheduler.croco_client = self.mock_croco
        scheduler.crm_client = self.mock_crm

    def test_crocotime_work_begin_offset_parsing(self):
        """Verify that croco.py correctly parses Unix offsets to HH:MM:SS."""
        # Simulated timesheet items returned by CrocoTime API
        mock_response = {
            "result": {
                "TimeSheetWorkTime": {
                    "result": {
                        "root": {
                            "items": [
                                {
                                    "employee_id": 1291,
                                    "display_name": "IT102 Алияр Аскаров",
                                    "days": [
                                        {
                                            "day": 1780531200,
                                            "summary_time": 30230,
                                            "work_begin": 32598,  # 9:03:18 AM
                                            "work_end": 66011
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                }
            }
        }

        # Mock request response
        mock_post = MagicMock()
        mock_post.status_code = 200
        mock_post.json.return_value = mock_response

        client = croco.CrocoClient("http://fake-croco/", "user", "pass", token_file="fake.json")
        client.session_id = "fake-session"

        with patch("requests.post", return_value=mock_post):
            times = client.get_work_start_times("2026-06-04")
            
            self.assertIn("IT102 Алияр Аскаров", times)
            self.assertEqual(times["IT102 Алияр Аскаров"]["time_str"], "09:03:18")
            self.assertEqual(times["IT102 Алияр Аскаров"]["seconds"], 32598)

    def test_scheduler_crocotime_checkin_and_lateness_detection(self):
        """Verify scheduler detects checkins and determines lateness correctly."""
        today_str = "2026-06-04"
        
        # Mock Sheets to return employees list
        self.mock_sheets.get_employees.return_value = [
            {
                "ФИО": "Александр Кузнецов",
                "Есть CrocoTime": "Да",
                "Croco ID": "IT116",
                "Время начала": "09:00:00",
                "Дней подряд": 4
            }
        ]
        
        # No check-ins logged yet today
        self.mock_sheets.get_checkins_for_date.return_value = []
        
        # Mock CrocoClient to return start times (one late start)
        self.mock_croco.get_work_start_times.return_value = {
            "IT116 Кузнецов Александр": {
                "time_str": "09:03:18",
                "seconds": 32598, # 9:03:18
                "work_end": 66011
            }
        }
        
        # Mock telegram app context
        mock_app = MagicMock()
        
        # Run poll
        asyncio.run(scheduler.poll_crocotime_work_start(mock_app, today_str))
        
        # Verify log_checkin was called with status 'Опоздал'
        self.mock_sheets.log_checkin.assert_called_once_with(
            date_str=today_str,
            name="Александр Кузнецов",
            time_str="09:03:18",
            checkin_type="CrocoTime",
            status="Опоздал"
        )

    def test_crm_tasks_filtering(self):
        """Verify CRMClient fetches active tasks and excludes completed ones."""
        mock_response = {
            "data": [
                {
                    "uuid": "task-uuid-1",
                    "subject": "Внедрение системы чекинов",
                    "status": {"name": "В работе"},
                    "responsible": {"first_name": "Александр"}
                },
                {
                    "uuid": "task-uuid-2",
                    "subject": "Аудит серверов",
                    "status": {"name": "Завершено"},
                    "responsible": {"first_name": "Александр"}
                }
            ]
        }
        
        mock_post = MagicMock()
        mock_post.status_code = 200
        mock_post.json.return_value = mock_response

        mock_get = MagicMock()
        mock_get.status_code = 200
        mock_get.json.return_value = [{"name": "Александр 116", "uuid": "fake-preset-116"}]

        client = crm.CRMClient(token_file="fake.json")
        client.access_token = "fake-access"

        with patch("requests.post", return_value=mock_post), \
             patch("requests.get", return_value=mock_get):
            tasks = client.get_active_tasks("116")
            
            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0]["uuid"], "task-uuid-1")
            self.assertEqual(tasks[0]["subject"], "Внедрение системы чекинов")
            self.assertEqual(tasks[0]["status"], "В работе")

    def test_streak_increment_and_reset(self):
        """Verify evening job updates streaks and triggers milestones correctly."""
        today_str = "2026-06-04"
        mock_app = MagicMock()
        
        # Employees list: Alexandre has 4 days streak, Igor has 3 days
        self.mock_sheets.get_employees.return_value = [
            {
                "ФИО": "Александр Кузнецов",
                "Дней подряд": 4,
                "Текущая ачивка": ""
            },
            {
                "ФИО": "Игорь Зносок",
                "Дней подряд": 3,
                "Текущая ачивка": ""
            }
        ]
        
        # Today's check-ins: Alexandre is 'Вовремя', Igor is 'Опоздал'
        self.mock_sheets.get_checkins_for_date.return_value = [
            {"ФИО": "Александр Кузнецов", "Статус": "Вовремя"},
            {"ФИО": "Игорь Зносок", "Статус": "Опоздал"}
        ]
        
        # Mock state to return group chat ID
        with patch("config.load_state", return_value={"group_chat_id": 123456}):
            asyncio.run(scheduler.check_daily_streaks(mock_app, today_str))
            
            # Verify Alexandre's streak was updated to 5, achievement set to "Красавчик"
            self.mock_sheets.update_employee_field.assert_any_call("Александр Кузнецов", "Дней подряд", 5)
            self.mock_sheets.update_employee_field.assert_any_call("Александр Кузнецов", "Текущая ачивка", "Красавчик")
            
            # Verify Igor's streak was reset to 0
            self.mock_sheets.update_employee_field.assert_any_call("Игорь Зносок", "Дней подряд", 0)
            self.mock_sheets.update_employee_field.assert_any_call("Игорь Зносок", "Текущая ачивка", "")

    def test_text_handler_respects_request_plan_setting(self):
        """Verify that text_handler handles plan requests according to sheet settings."""
        # Bind sheets_client
        bot.sheets_client = self.mock_sheets
        
        # Mock find_employee_by_tg_id
        employee_has_plan = {
            "ФИО": "Александр Кузнецов",
            "Telegram User ID": "12345",
            "Запрашивать план": "Да",
            "Есть CrocoTime": "Да"
        }
        employee_no_plan = {
            "ФИО": "Олег Пенкин",
            "Telegram User ID": "67890",
            "Запрашивать план": "Нет",
            "Есть CrocoTime": "Да"
        }
        
        def mock_find(user_id):
            if user_id == "12345":
                return employee_has_plan
            elif user_id == "67890":
                return employee_no_plan
            return None
            
        with patch("bot.find_employee_by_tg_id", side_effect=mock_find):
            # Test case 1: Employee with 'Запрашивать план' == 'Да'
            mock_update = MagicMock()
            mock_update.effective_user.id = 12345
            mock_update.message.chat.type = "private"
            mock_update.message.text = "Мой план на сегодня: сделать тест."
            mock_update.message.reply_text = AsyncMock()
            
            mock_context = MagicMock()
            mock_context.bot.send_message = AsyncMock()
            
            # Mock config.load_state and save_state to avoid editing real state
            fake_state = {"group_chat_id": 999}
            with patch("config.load_state", return_value=fake_state), \
                 patch("config.save_state") as mock_save_state:
                
                asyncio.run(bot.text_handler(mock_update, mock_context))
                
                # Verify plan is logged
                self.mock_sheets.log_task_plan.assert_called_once()
                self.assertIn("Александр Кузнецов", fake_state["submitted_plans"][datetime.now().strftime("%Y-%m-%d")])
                mock_update.message.reply_text.assert_called_once()
                
            # Test case 2: Employee with 'Запрашивать план' == 'Нет' (already checked in)
            self.mock_sheets.log_task_plan.reset_mock()
            mock_update_no_plan = MagicMock()
            mock_update_no_plan.effective_user.id = 67890
            mock_update_no_plan.message.chat.type = "private"
            mock_update_no_plan.message.text = "Привет"
            mock_update_no_plan.message.reply_text = AsyncMock()
            
            # Already checked in
            self.mock_sheets.get_checkins_for_date.return_value = [{"ФИО": "Олег Пенкин", "Статус": "Вовремя"}]
            
            with patch("config.load_state", return_value={"group_chat_id": 999}):
                asyncio.run(bot.text_handler(mock_update_no_plan, mock_context))
                # Should NOT log task plan
                self.mock_sheets.log_task_plan.assert_not_called()
                # Should NOT reply with anything since already checked in
                mock_update_no_plan.message.reply_text.assert_not_called()
                
            # Test case 3: Employee with 'Запрашивать план' == 'Нет' (not checked in yet, CrocoTime employee)
            self.mock_sheets.get_checkins_for_date.return_value = []
            mock_update_no_plan.message.reply_text.reset_mock()
            with patch("config.load_state", return_value={"group_chat_id": 999}):
                asyncio.run(bot.text_handler(mock_update_no_plan, mock_context))
                # Should reply with instructions for CrocoTime
                mock_update_no_plan.message.reply_text.assert_called_with(
                    "Привет! У вас не запрашивается план на день.\n"
                    "Для отметки о начале дня, пожалуйста, запустите CrocoTime."
                )

    def test_group_sync_and_auto_registration(self):
        """Verify group members sync, join/leave tracking and auto-registration handlers."""
        bot.sheets_client = self.mock_sheets
        # 1. Test /sync command
        mock_update = MagicMock()
        mock_update.effective_chat.type = "supergroup"
        mock_update.effective_chat.id = 12345
        mock_update.effective_chat.title = "Красавчики"
        mock_update.effective_user.id = 55555
        mock_update.message.reply_text = AsyncMock()
        
        mock_context = MagicMock()
        
        # Mock administrators in group
        admin1 = MagicMock()
        admin1.user.is_bot = False
        admin1.user.id = 11111
        admin1.user.username = "admin_one"
        admin1.user.first_name = "First"
        admin1.user.last_name = "Admin"
        
        mock_update.effective_chat.get_administrators = AsyncMock(return_value=[admin1])
        
        # User is admin check
        mock_member = MagicMock()
        mock_member.status = "creator"
        mock_update.effective_chat.get_member = AsyncMock(return_value=mock_member)
        
        with patch("config.load_state", return_value={"group_chat_id": 12345}), \
             patch("config.save_state"):
             
            asyncio.run(bot.sync_members(mock_update, mock_context))
            
            # Verify Sheets API called
            self.mock_sheets.add_or_update_employee.assert_called_with(
                "First Admin", "admin_one", "11111"
            )
            mock_update.message.reply_text.assert_any_call("🔄 Синхронизирую участников группы с Google Таблицей...")
            
        # 2. Test chat_member_handler (Join)
        self.mock_sheets.add_or_update_employee.reset_mock()
        mock_join_update = MagicMock()
        mock_join_update.chat_member.chat.id = 12345
        mock_join_update.chat_member.old_chat_member.status = "left"
        mock_join_update.chat_member.new_chat_member.status = "member"
        mock_join_update.chat_member.new_chat_member.user.is_bot = False
        mock_join_update.chat_member.new_chat_member.user.id = 22222
        mock_join_update.chat_member.new_chat_member.user.username = "new_joiner"
        mock_join_update.chat_member.new_chat_member.user.first_name = "New"
        mock_join_update.chat_member.new_chat_member.user.last_name = "User"
        
        with patch("config.load_state", return_value={"group_chat_id": 12345}):
            asyncio.run(bot.chat_member_handler(mock_join_update, mock_context))
            self.mock_sheets.add_or_update_employee.assert_called_with(
                "New User", "new_joiner", "22222"
            )
            
        # 3. Test group_message_handler (Auto-register when typing in group)
        self.mock_sheets.add_or_update_employee.reset_mock()
        mock_group_msg_update = MagicMock()
        mock_group_msg_update.effective_chat.id = 12345
        mock_group_msg_update.effective_user.is_bot = False
        mock_group_msg_update.effective_user.id = 33333
        mock_group_msg_update.effective_user.username = "active_writer"
        mock_group_msg_update.effective_user.first_name = "Active"
        mock_group_msg_update.effective_user.last_name = "Writer"
        
        with patch("config.load_state", return_value={"group_chat_id": 12345}):
            asyncio.run(bot.group_message_handler(mock_group_msg_update, mock_context))
            self.mock_sheets.add_or_update_employee.assert_called_with(
                "Active Writer", "active_writer", "33333"
            )

    def test_dynamic_morning_requests(self):
        """Verify that check_and_send_morning_requests sends combined geo/CRM plans 10 mins before start."""
        # Setup mock employees
        # 1. Alexandre: wants_plan='Да', needs_geo='Да' (Есть CrocoTime='Нет'), start time 09:00:00.
        # Target time: 08:50:00
        # 2. Oleg: wants_plan='Да', needs_geo='Нет' (Есть CrocoTime='Да'), start time 10:00:00.
        # Target time: 09:50:00
        self.mock_sheets.get_employees.return_value = [
            {
                "ФИО": "Александр Кузнецов",
                "Telegram User ID": "11111",
                "Запрашивать план": "Да",
                "Есть CrocoTime": "Нет",
                "Время начала": "09:00:00",
                "CRM ID": "crm-alex"
            },
            {
                "ФИО": "Олег Пенкин",
                "Telegram User ID": "22222",
                "Запрашивать план": "Да",
                "Есть CrocoTime": "Да",
                "Время начала": "10:00:00",
                "CRM ID": "crm-oleg"
            }
        ]

        # Mock CRM tasks for Alexandre
        self.mock_crm.get_active_tasks.return_value = [
            {"subject": "Задача 1", "url": "http://crm/1", "status": "В работе"}
        ]

        mock_app = MagicMock()
        mock_app.bot.send_message = AsyncMock()

        # Let's test at 08:49:00 (too early for both)
        dt_early = datetime(2026, 6, 10, 8, 49, 0)
        fake_state = {}
        with patch("config.load_state", return_value=fake_state), \
             patch("config.save_state") as mock_save:
            asyncio.run(scheduler.check_and_send_morning_requests(mock_app, "2026-06-10", dt_early))
            # No messages should be sent
            mock_app.bot.send_message.assert_not_called()

        # Let's test at 08:50:00 (exact time for Alexandre, but too early for Oleg)
        dt_alex_time = datetime(2026, 6, 10, 8, 50, 0)
        mock_app.bot.send_message.reset_mock()
        fake_state = {}
        with patch("config.load_state", return_value=fake_state), \
             patch("config.save_state") as mock_save:
            asyncio.run(scheduler.check_and_send_morning_requests(mock_app, "2026-06-10", dt_alex_time))
            # Alexandre should receive 1 combined message
            self.assertEqual(mock_app.bot.send_message.call_count, 1)
            args, kwargs = mock_app.bot.send_message.call_args
            self.assertEqual(kwargs["chat_id"], "11111")
            # Should contain geo request and crm tasks list
            self.assertIn("📍 Пожалуйста, отправь свою геопозицию для чекина", kwargs["text"])
            self.assertIn("📝 Сегодня на тебе висят следующие задачи в CRM:", kwargs["text"])
            self.assertIn("Задача 1", kwargs["text"])
            # Saved state should mark Alexandre as sent
            self.assertIn("Александр Кузнецов", fake_state["sent_morning_requests"]["2026-06-10"])
            # Oleg should not be marked as sent yet
            self.assertNotIn("Олег Пенкин", fake_state["sent_morning_requests"]["2026-06-10"])

        # Let's test at 09:50:00 (already sent Alexandre, now sending Oleg)
        dt_oleg_time = datetime(2026, 6, 10, 9, 50, 0)
        mock_app.bot.send_message.reset_mock()
        # Mock CRM tasks for Oleg to be empty
        self.mock_crm.get_active_tasks.return_value = []
        fake_state = {
            "sent_morning_requests": {
                "2026-06-10": ["Александр Кузнецов"]
            }
        }
        with patch("config.load_state", return_value=fake_state), \
             patch("config.save_state") as mock_save:
            asyncio.run(scheduler.check_and_send_morning_requests(mock_app, "2026-06-10", dt_oleg_time))
            # Oleg should receive 1 message, Alexandre should be skipped
            self.assertEqual(mock_app.bot.send_message.call_count, 1)
            args, kwargs = mock_app.bot.send_message.call_args
            self.assertEqual(kwargs["chat_id"], "22222")
            # Should NOT contain geo request (he has CrocoTime)
            self.assertNotIn("📍 Пожалуйста, отправь свою геопозицию для чекина", kwargs["text"])
            # Should say no tasks in CRM
            self.assertIn("📝 На сегодня у тебя нет активных задач в CRM.", kwargs["text"])
            self.assertIn("Олег Пенкин", fake_state["sent_morning_requests"]["2026-06-10"])

if __name__ == "__main__":
    unittest.main()
