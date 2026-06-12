import os
import json
import hashlib
import requests
from datetime import datetime, timezone

class CrocoClient:
    def __init__(self, base_url, email, password, token_file="token_store.json"):
        self.base_url = base_url.rstrip("/") + "/"
        self.email = email
        self.password = password
        self.token_file = token_file
        self.session_id = None
        self._load_session()

    def _load_session(self):
        if os.path.exists(self.token_file):
            try:
                with open(self.token_file, "r") as f:
                    data = json.load(f)
                    self.session_id = data.get("croco_session")
            except Exception:
                pass

    def _save_session(self, session_id):
        self.session_id = session_id
        data = {}
        if os.path.exists(self.token_file):
            try:
                with open(self.token_file, "r") as f:
                    data = json.load(f)
            except Exception:
                pass
        data["croco_session"] = session_id
        try:
            with open(self.token_file, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"[Croco] Failed to save session to {self.token_file}: {e}")

    def login(self):
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        md5_password = hashlib.md5(self.password.encode('utf-8')).hexdigest()
        
        logins_to_try = [self.email, self.email.split("@")[0]]
        request_names = ["Logon", "SimpleLogon"]
        
        for req_name in request_names:
            for login_val in logins_to_try:
                payload = {
                    "controller": "LogonController",
                    "revalidate_hash": "9eb5da2904f502ac3428ad72f9a2f603",
                    "query": {
                        "user": {
                            "login": login_val,
                            "password": md5_password
                        }
                    },
                    "subsystems": [
                        {
                            "uuid": "com.infomaximum.crocotime",
                            "app_version": "5.8.11"
                        }
                    ],
                    "app_version": "5.8.11"
                }
                try:
                    res = requests.post(self.base_url, json=payload, headers=headers, timeout=10)
                    if res.status_code == 200:
                        res_json = res.json()
                        session = res_json.get("session") or res_json.get("session_id") or res_json.get("result", {}).get("session")
                        if session:
                            self._save_session(session)
                            print(f"[Croco] Successfully logged in using {req_name} ({login_val})")
                            return True
                except Exception as e:
                    print(f"[Croco] Logon attempt failed: {e}")
        return False

    def get_work_start_times(self, date_str):
        """
        Fetch workday start times for all active employees on date_str (YYYY-MM-DD).
        Returns a dict mapping employee name/id to (work_begin_time_str, raw_seconds).
        """
        if not self.session_id:
            if not self.login():
                print("[Croco] Authentication failed. Cannot fetch start times.")
                return {}

        # Parse date and build UTC boundaries
        try:
            start_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            start_ts = int(start_dt.timestamp())
            end_ts = start_ts + 86400
        except Exception as e:
            print(f"[Croco] Invalid date format {date_str}: {e}")
            return {}

        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        cookies = {"session": self.session_id}

        payload = {
            "controller": "BatchProcessing",
            "revalidate_hash": "9eb5da2904f502ac3428ad72f9a2f603",
            "query": {
                "items": [
                    {
                        "name": "TimeSheetWorkTime",
                        "controller": "timesheet_report",
                        "params": {
                            "interval": [start_ts, end_ts],
                            "columns": {
                                "visible_columns": ["WORK_BEGIN", "WORK_END", "SUMMARY"]
                            },
                            "write_empty": 0,
                            "view": 1,
                            "type": 1  # LATE mode retrieves work_begin and work_end
                        },
                        "subsystems": [{"uuid": "com.infomaximum.crocotime", "app_version": "5.8.11"}],
                        "app_version": "5.8.11"
                    }
                ]
            },
            "app_version": "5.8.11"
        }

        try:
            res = requests.post(self.base_url, json=payload, headers=headers, cookies=cookies, timeout=15)
            if res.status_code == 200:
                body = res.json()
                
                # Check for session expiration or unauthorized error
                result_data = body.get("result", {})
                timesheet_report_data = result_data.get("TimeSheetWorkTime", {})
                
                if "error" in timesheet_report_data:
                    err = timesheet_report_data["error"]
                    if err.get("code") in ["invalid_logon", "unauthorized", "invalid_session"]:
                        print("[Croco] Session expired. Relogging...")
                        self.session_id = None
                        if self.login():
                            return self.get_work_start_times(date_str)
                    print(f"[Croco] API error: {err}")
                    return {}

                timesheet_result = timesheet_report_data.get("result", {})
                timesheet_items = timesheet_result.get("root", {}).get("items", [])
                
                start_times = {}
                for item in timesheet_items:
                    display_name = item.get("display_name", "")
                    days = item.get("days", [])
                    
                    # Look for day item matching today
                    day_data = None
                    for d in days:
                        if d.get("day") == start_ts:
                            day_data = d
                            break
                    
                    if day_data and day_data.get("summary_time", 0) > 0:
                        work_begin = day_data.get("work_begin")
                        if work_begin is not None:
                            hours = work_begin // 3600
                            minutes = (work_begin % 3600) // 60
                            seconds = work_begin % 60
                            time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                            
                            start_times[display_name] = {
                                "time_str": time_str,
                                "seconds": work_begin,
                                "work_end": day_data.get("work_end")
                            }
                return start_times
            else:
                print(f"[Croco] Request failed with HTTP {res.status_code}")
        except Exception as e:
            print(f"[Croco] Failed to query timesheet: {e}")
            
        return {}
