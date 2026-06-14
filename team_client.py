import requests
import json
from datetime import datetime
import re

class TeamClient:
    def __init__(self, login, password):
        self.base_url = 'https://bi.asista.kz/api'
        self.login_cred = login
        self.password = password
        self.token = None
        self.session = requests.Session()
        self.session.headers.update({
            'origin': 'https://team.itsp.kz',
            'referer': 'https://team.itsp.kz/'
        })
        self._statuses_cache = None
        self._table_cache = {}
        
    def login(self):
        try:
            res = self.session.post(f'{self.base_url}/login/lk-auth', json={
                'login': self.login_cred,
                'password': self.password,
                'refresh': True
            })
            data = res.json()
            if data.get('result'):
                self.token = data['data']['hash']
                self.session.headers.update({'Authorization': f'Bearer {self.token}'})
                return True
        except Exception as e:
            print(f"[TeamClient] Login failed: {e}")
        return False

    def get_statuses(self):
        if self._statuses_cache:
            return self._statuses_cache
            
        try:
            res = self.session.get(f'{self.base_url}/itsp-assistant/statuses-management/list?enabled=true')
            data = res.json()
            if data.get('result'):
                self._statuses_cache = data.get('list', [])
                return self._statuses_cache
        except Exception as e:
            print(f"[TeamClient] Failed to fetch statuses: {e}")
        return []

    def get_status_uuid_by_short_name(self, short_name):
        statuses = self.get_statuses()
        for s in statuses:
            if s.get('short_name') == short_name:
                return s.get('uuid')
        return None

    def get_table_for_month(self, year, month):
        cache_key = f"{year}-{month}"
        if cache_key in self._table_cache:
            return self._table_cache[cache_key]
            
        try:
            res = self.session.get(f'{self.base_url}/itsp-assistant/work-hours/tables/{year}')
            tables = res.json().get('months', [])
            table_uuid = None
            for t in tables:
                if t['month'] == month:
                    table_uuid = t['uuid']
                    break
            
            if not table_uuid:
                return None
                
            res = self.session.get(f'{self.base_url}/itsp-assistant/work-hours/table/{table_uuid}')
            data = res.json()
            if data.get('result'):
                self._table_cache[cache_key] = data
                return data
        except Exception as e:
            print(f"[TeamClient] Failed to fetch table for {year}-{month}: {e}")
        return None

    def _extract_it_number(self, croco_id):
        if not croco_id:
            return None
        m = re.search(r'IT\s*(\d+)', croco_id, re.IGNORECASE)
        if m:
            return str(int(m.group(1))) # normalize, e.g. "0162" -> "162"
        return None

    def _find_implementer(self, node, it_number):
        if 'implementers' in node:
            for imp in node['implementers']:
                if str(imp.get('it')) == it_number:
                    return imp
        if 'subdivisions' in node:
            for sub in node['subdivisions']:
                found = self._find_implementer(sub, it_number)
                if found:
                    return found
        return None

    def get_user_status_for_date(self, croco_id, date_str):
        """Returns True if user has a valid excuse (vacation/sickday) for the date."""
        if not self.token and not self.login():
            return False
            
        it_number = self._extract_it_number(croco_id)
        if not it_number:
            return False
            
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        table_data = self.get_table_for_month(dt.year, dt.month)
        if not table_data:
            return False
            
        for node in table_data.get('list', []):
            imp = self._find_implementer(node, it_number)
            if imp:
                for wh in imp.get('work_hours', []):
                    if wh.get('date') == date_str:
                        status_uuid = wh.get('status_uuid')
                        if status_uuid:
                            # check if it's a valid excuse
                            statuses = self.get_statuses()
                            for s in statuses:
                                if s.get('uuid') == status_uuid:
                                    # Only Vacation (ОТ) and Sickday (Б, БО) freeze the streak
                                    if s.get('short_name') in ['ОТ', 'Б', 'БО']:
                                        return True
                break
        return False

    def mark_lateness(self, croco_id, date_str):
        """Sets the 'О' (Lateness) status for the user on the given date."""
        if not self.token and not self.login():
            return False
            
        it_number = self._extract_it_number(croco_id)
        if not it_number:
            return False
            
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        table_data = self.get_table_for_month(dt.year, dt.month)
        if not table_data:
            return False
            
        user_uuid = None
        for node in table_data.get('list', []):
            imp = self._find_implementer(node, it_number)
            if imp:
                user_uuid = imp.get('uuid')
                break
                
        if not user_uuid:
            print(f"[TeamClient] Implementer not found for croco_id {croco_id}")
            return False
            
        status_uuid = self.get_status_uuid_by_short_name('О')
        if not status_uuid:
            print("[TeamClient] Lateness status 'О' not found in statuses list")
            return False
            
        payload = {
            "list": [
                {
                    "user_uuid": user_uuid,
                    "date": date_str,
                    "status_uuid": status_uuid,
                    "comment": "",
                    "worked_time": 0,
                    "user_version": 0
                }
            ]
        }
        
        try:
            res = self.session.post(f'{self.base_url}/itsp-assistant/work-hours/set/batch', json=payload)
            if res.status_code == 201:
                print(f"[TeamClient] Successfully marked lateness for {croco_id} on {date_str}")
                return True
            else:
                print(f"[TeamClient] Failed to mark lateness: {res.status_code} {res.text}")
        except Exception as e:
            print(f"[TeamClient] Exception marking lateness: {e}")
            
        return False

# Single global instance
team_client = None

def init_team_client(login, password):
    global team_client
    team_client = TeamClient(login, password)
    return team_client
