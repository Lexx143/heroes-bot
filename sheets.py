import os
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

class SheetsClient:
    def __init__(self, creds_file, sheet_title, share_email):
        self.creds_file = creds_file
        self.sheet_title = sheet_title
        self.share_email = share_email
        self.gc = None
        self.spreadsheet = None
        self._authenticate()

    def _authenticate(self):
        if not os.path.exists(self.creds_file):
            raise FileNotFoundError(
                f"[Sheets] Credentials file '{self.creds_file}' not found.\n"
                "Please place your Google Cloud Service Account JSON key in this file."
            )
        
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_file(self.creds_file, scopes=scopes)
        self.gc = gspread.authorize(creds)
        self._init_spreadsheet()

    def _init_spreadsheet(self):
        try:
            # Try to open existing spreadsheet
            self.spreadsheet = self.gc.open(self.sheet_title)
            print(f"[Sheets] Opened existing spreadsheet: '{self.sheet_title}'")
            self._ensure_worksheets()
        except gspread.SpreadsheetNotFound:
            # Create a new one
            print(f"[Sheets] Spreadsheet not found. Creating a new one: '{self.sheet_title}'...")
            self.spreadsheet = self.gc.create(self.sheet_title)
            
            # Share with user's email
            if self.share_email:
                try:
                    self.spreadsheet.share(self.share_email, perm_type='user', role='writer', notify=True)
                    print(f"[Sheets] Shared spreadsheet with '{self.share_email}' as Editor.")
                except Exception as e:
                    print(f"[Sheets] Failed to share spreadsheet with '{self.share_email}': {e}")
            
            # Initialize default sheets
            self._setup_worksheets()

    def _ensure_worksheets(self):
        """Ensures all worksheets exist with headers, without clearing existing data."""
        # 1. 'Сотрудники'
        try:
            self.spreadsheet.worksheet("Сотрудники")
        except gspread.WorksheetNotFound:
            ws_emp = self.spreadsheet.add_worksheet("Сотрудники", rows=100, cols=10)
            ws_emp.update("A1:J1", [[
                "ФИО", "Telegram Username", "Telegram User ID", 
                "Есть CrocoTime", "Croco ID", "CRM ID", 
                "Время начала", "Запрашивать план", "Текущая ачивка", "Дней подряд"
            ]])

        # 2. 'Журнал чекинов'
        try:
            self.spreadsheet.worksheet("Журнал чекинов")
        except gspread.WorksheetNotFound:
            ws_log = self.spreadsheet.add_worksheet("Журнал чекинов", rows=1000, cols=7)
            ws_log.update("A1:G1", [[
                "Дата", "ФИО", "Время отметки", "Тип", "Статус", "Координаты", "Ссылка на карту"
            ]])

        # 3. 'Планы задач'
        try:
            self.spreadsheet.worksheet("Планы задач")
        except gspread.WorksheetNotFound:
            ws_plan = self.spreadsheet.add_worksheet("Планы задач", rows=1000, cols=3)
            ws_plan.update("A1:C1", [[
                "Дата", "ФИО", "Текст плана / Статус задач"
            ]])

    def _setup_worksheets(self):
        # 1. Employees sheet (Сотрудники)
        # 2. Check-in log (Журнал чекинов)
        # 3. Tasks plan log (Планы задач)
        
        # Setup 'Сотрудники'
        try:
            ws_emp = self.spreadsheet.worksheet("Сотрудники")
        except gspread.WorksheetNotFound:
            ws_emp = self.spreadsheet.add_worksheet("Сотрудники", rows=100, cols=10)
        
        ws_emp.clear()
        ws_emp.update("A1:J1", [[
            "ФИО", "Telegram Username", "Telegram User ID", 
            "Есть CrocoTime", "Croco ID", "CRM ID", 
            "Время начала", "Запрашивать план", "Текущая ачивка", "Дней подряд"
        ]])

        # Setup 'Журнал чекинов'
        try:
            ws_log = self.spreadsheet.worksheet("Журнал чекинов")
        except gspread.WorksheetNotFound:
            ws_log = self.spreadsheet.add_worksheet("Журнал чекинов", rows=1000, cols=7)
        ws_log.clear()
        ws_log.update("A1:G1", [[
            "Дата", "ФИО", "Время отметки", "Тип", "Статус", "Координаты", "Ссылка на карту"
        ]])

        # Setup 'Планы задач'
        try:
            ws_plan = self.spreadsheet.worksheet("Планы задач")
        except gspread.WorksheetNotFound:
            ws_plan = self.spreadsheet.add_worksheet("Планы задач", rows=1000, cols=3)
        ws_plan.clear()
        ws_plan.update("A1:C1", [[
            "Дата", "ФИО", "Текст плана / Статус задач"
        ]])
        
        # Remove default 'Sheet1' if it exists
        try:
            default_sheet = self.spreadsheet.worksheet("Sheet1")
            self.spreadsheet.del_worksheet(default_sheet)
        except Exception:
            pass

    def get_employees(self):
        """Returns all employee rows as list of dicts."""
        ws = self.spreadsheet.worksheet("Сотрудники")
        return ws.get_all_records()

    def update_employee_field(self, name, field, value):
        """Update a specific field for an employee by their ФИО."""
        ws = self.spreadsheet.worksheet("Сотрудники")
        records = ws.get_all_records()
        
        row_idx = -1
        for idx, r in enumerate(records):
            if r.get("ФИО") == name:
                row_idx = idx + 2  # 1-indexed + header row
                break
                
        if row_idx == -1:
            print(f"[Sheets] Employee '{name}' not found in 'Сотрудники' sheet.")
            return False

        headers = ws.row_values(1)
        if field not in headers:
            print(f"[Sheets] Field '{field}' not found in 'Сотрудники' headers.")
            return False
            
        col_idx = headers.index(field) + 1
        ws.update_cell(row_idx, col_idx, value)
        return True

    def log_checkin(self, date_str, name, time_str, checkin_type, status, coordinates="", map_link=""):
        """Logs a check-in event to the log sheet."""
        ws = self.spreadsheet.worksheet("Журнал чекинов")
        ws.append_row([date_str, name, time_str, checkin_type, status, coordinates, map_link])

    def log_task_plan(self, date_str, name, plan_text):
        """Logs a daily plan/status to the plan sheet."""
        ws = self.spreadsheet.worksheet("Планы задач")
        ws.append_row([date_str, name, plan_text])

    def get_checkins_for_date(self, date_str):
        """Returns check-ins logged for a specific date."""
        ws = self.spreadsheet.worksheet("Журнал чекинов")
        records = ws.get_all_records()
        return [r for r in records if r.get("Дата") == date_str]

    def add_or_update_employee(self, name, username, user_id):
        """Adds a new employee or updates an existing one if their name/username/user_id matches."""
        ws = self.spreadsheet.worksheet("Сотрудники")
        records = ws.get_all_records()
        
        found_idx = -1
        for idx, r in enumerate(records):
            r_user_id = str(r.get("Telegram User ID", "")).strip()
            r_username = str(r.get("Telegram Username", "")).strip()
            r_name = str(r.get("ФИО", "")).strip()
            
            if ((r_user_id and r_user_id == str(user_id)) or 
                (username and r_username.lower() == str(username).lower()) or
                (r_name.lower() == name.lower())):
                found_idx = idx + 2
                break
                
        if found_idx != -1:
            # Update fields if they are missing
            headers = ws.row_values(1)
            # Update TG User ID
            if "Telegram User ID" in headers:
                col = headers.index("Telegram User ID") + 1
                if not records[found_idx - 2].get("Telegram User ID"):
                    ws.update_cell(found_idx, col, str(user_id))
            # Update Username
            if username and "Telegram Username" in headers:
                col = headers.index("Telegram Username") + 1
                if not records[found_idx - 2].get("Telegram Username"):
                    ws.update_cell(found_idx, col, username)
            print(f"[Sheets] Updated existing employee '{name}' details.")
            return False  # Existing
        else:
            # Insert new row
            ws.append_row([
                name, username or "", str(user_id), "Нет", "", "", "09:00:00", "Да", "", 0
            ])
            print(f"[Sheets] Added new employee '{name}' to sheet.")
            return True  # New

    def remove_employee(self, name=None, username=None, user_id=None):
        """Removes an employee row from the 'Сотрудники' sheet."""
        ws = self.spreadsheet.worksheet("Сотрудники")
        records = ws.get_all_records()
        
        row_idx = -1
        for idx, r in enumerate(records):
            r_user_id = str(r.get("Telegram User ID", "")).strip()
            r_username = str(r.get("Telegram Username", "")).strip()
            r_name = str(r.get("ФИО", "")).strip()
            
            if ((user_id and r_user_id == str(user_id)) or
                (username and r_username.lower() == username.lower()) or
                (name and r_name.lower() == name.lower())):
                row_idx = idx + 2
                break
                
        if row_idx != -1:
            ws.delete_rows(row_idx)
            print(f"[Sheets] Removed employee row {row_idx}.")
            return True
        return False

    @staticmethod
    def get_employee_start_time(emp, now_dt):
        """
        Determine the start time for the employee based on the day of the week.
        Supports overrides like 'ПН Время начала', 'ВТ Время начала', etc.
        """
        weekday_cols = {
            0: "ПН Время начала",
            1: "ВТ Время начала",
            2: "СР Время начала",
            3: "ЧТ Время начала",
            4: "ПТ Время начала"
        }
        
        day_col = weekday_cols.get(now_dt.weekday())
        start_time_str = None
        
        # Check specific weekday column
        if day_col and emp.get(day_col):
            val = str(emp.get(day_col)).strip()
            if val:
                start_time_str = val
                
        # Fallback to general start time
        if not start_time_str:
            start_time_str = str(emp.get("Время начала", "09:00:00")).strip()
            
        # Ensure it has seconds
        if len(start_time_str.split(":")) == 2:
            start_time_str += ":00"
            
        return start_time_str
