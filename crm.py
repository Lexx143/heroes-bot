import os
import sys
import json
import requests

class CRMClient:
    def __init__(self, token_file="token_store.json"):
        self.token_file = token_file
        self.refresh_url = "https://api-crm.asista.kz/auth/refresh"
        self.list_url = "https://api-crm.asista.kz/tasks/list"
        self.access_token = None

    def _load_refresh_token(self):
        if os.path.exists(self.token_file):
            try:
                with open(self.token_file, "r") as f:
                    data = json.load(f)
                    return data.get("refresh_token")
            except Exception as e:
                print(f"[CRM] Failed to load refresh token from {self.token_file}: {e}")
        return None

    def _save_refresh_token(self, token):
        data = {}
        if os.path.exists(self.token_file):
            try:
                with open(self.token_file, "r") as f:
                    data = json.load(f)
            except Exception:
                pass
        data["refresh_token"] = token
        try:
            with open(self.token_file, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"[CRM] Failed to save refresh token to {self.token_file}: {e}")

    def refresh_access_token(self):
        refresh_token = self._load_refresh_token()
        if not refresh_token:
            print("[CRM] Error: No refresh token available in token_store.json.")
            return False

        headers = {
            'accept': 'application/json, text/plain, */*',
            'origin': 'https://crm.asista.kz',
            'referer': 'https://crm.asista.kz/',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        try:
            response = requests.post(
                self.refresh_url,
                headers=headers,
                cookies={"refresh_token": refresh_token},
                timeout=15
            )
            if response.status_code == 201:
                res_data = response.json()
                self.access_token = res_data.get("access_token")
                
                # Check if a new refresh token was set in cookies
                if "refresh_token" in response.cookies:
                    self._save_refresh_token(response.cookies["refresh_token"])
                return True
            else:
                print(f"[CRM] Failed to refresh token. Status: {response.status_code}, Response: {response.text}")
        except Exception as e:
            print(f"[CRM] Token refresh exception: {e}")
        return False

    def get_active_tasks(self, employee_crm_id):
        """
        Fetch active (non-completed) tasks for a specific employee ID or UUID.
        """
        if not self.access_token:
            if not self.refresh_access_token():
                return []

        # Resolve preset UUID dynamically if employee_crm_id is a short ID (e.g., "162")
        preset_uuid = None
        if len(str(employee_crm_id)) == 36 and str(employee_crm_id).count("-") == 4:
            preset_uuid = str(employee_crm_id)
        else:
            try:
                headers_presets = {
                    'accept': 'application/json, text/plain, */*',
                    'authorization': f"Bearer {self.access_token}",
                    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
                res_presets = requests.get(
                    "https://api-crm.asista.kz/presets/list/tasks",
                    headers=headers_presets,
                    cookies={"refresh_token": self._load_refresh_token()},
                    timeout=15
                )
                if res_presets.status_code in [401, 403]:
                    if self.refresh_access_token():
                        headers_presets['authorization'] = f"Bearer {self.access_token}"
                        res_presets = requests.get(
                            "https://api-crm.asista.kz/presets/list/tasks",
                            headers=headers_presets,
                            cookies={"refresh_token": self._load_refresh_token()},
                            timeout=15
                        )
                
                if res_presets.status_code == 200:
                    presets = res_presets.json()
                    for p in presets:
                        p_name = p.get("name", "")
                        if str(employee_crm_id).lower() in p_name.lower():
                            preset_uuid = p.get("uuid")
                            print(f"[CRM] Resolved CRM ID '{employee_crm_id}' to preset '{p_name}' ({preset_uuid})")
                            break
            except Exception as e:
                print(f"[CRM] Failed to fetch presets list: {e}")

        if not preset_uuid:
            print(f"[CRM] Error: Could not resolve preset for CRM ID '{employee_crm_id}'")
            return []

        headers = {
            'accept': 'application/json, text/plain, */*',
            'authorization': f"Bearer {self.access_token}",
            'content-type': 'application/json',
            'origin': 'https://crm.asista.kz',
            'referer': 'https://crm.asista.kz/',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

        # Query all tasks for this preset.
        payload = {
            "extendedSearch": False,
            "search": "",
            "method": "data",
            "pagination": {
                "current": 1,
                "page_size": 100
            },
            "paranoid": False,
            "preset_uuid": preset_uuid,
            "table_search_fields": {
                "responsibles": [],
                "authors": [],
                "projects": [],
                "companies": [],
                "done_by_accounting": [],
                "bills_paid": [],
                "statuses": []
            }
        }

        try:
            res = requests.post(
                self.list_url,
                headers=headers,
                cookies={"refresh_token": self._load_refresh_token()},
                json=payload,
                timeout=15
            )
            
            # If token expired (HTTP 401/403 or similar), refresh and retry once
            if res.status_code in [401, 403]:
                print("[CRM] Access token expired during query. Refreshing...")
                if self.refresh_access_token():
                    headers['authorization'] = f"Bearer {self.access_token}"
                    res = requests.post(
                        self.list_url,
                        headers=headers,
                        cookies={"refresh_token": self._load_refresh_token()},
                        json=payload,
                        timeout=15
                    )
                else:
                    return []

            if res.status_code in [200, 201]:
                tasks = res.json().get("data", [])
                
                # Filter out completed tasks
                active_tasks = []
                for t in tasks:
                    status_name = t.get("status", {}).get("name", "")
                    if status_name != "Завершено":
                        active_tasks.append({
                            "uuid": t.get("uuid"),
                            "subject": t.get("subject"),
                            "status": status_name,
                            "url": f"https://crm.asista.kz/tasks/view/{t.get('uuid')}"
                        })
                return active_tasks
            else:
                print(f"[CRM] Failed to fetch tasks. Status: {res.status_code}, Response: {res.text}")
        except Exception as e:
            print(f"[CRM] Exception fetching tasks for {employee_crm_id}: {e}")

        return []
