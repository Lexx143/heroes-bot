import os
import re
import sys
import json
import hashlib
from datetime import datetime, timezone
import requests

TOKEN_FILE = "/Users/lexx/coding/projects/deus_bot/scratch/token_store.json"

def load_credentials():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            data = json.load(f)
            return (
                data.get("croco_url"),
                data.get("croco_login"),
                data.get("croco_password")
            )
    return None, None, None

def login(url, email, password):
    import hashlib
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    md5_password = hashlib.md5(password.encode('utf-8')).hexdigest()
    
    logins_to_try = [email, email.split("@")[0]]
    request_names = ["Logon", "SimpleLogon"]
    
    for req_name in request_names:
        for login_val in logins_to_try:
            payload = {
                "name": req_name,
                "controller": "LogonController",
                "params": {
                    "user": {
                        "login": login_val,
                        "password": md5_password
                    }
                }
            }
            try:
                print(f"Trying {req_name} with login '{login_val}'...")
                res = requests.post(url, json=payload, headers=headers, timeout=10)
                if res.status_code == 200:
                    res_json = res.json()
                    session = res_json.get("session") or res_json.get("session_id") or res_json.get("result", {}).get("session")
                    if session:
                        print(f"Success! Method: {req_name}, Login: {login_val}")
                        return session
                    else:
                        print(f"  No session in response: {res_json}")
                else:
                    print(f"  HTTP Status {res.status_code}: {res.text}")
            except Exception as e:
                print(f"  Attempt failed: {e}")
    return None

def test_controller(url, session, controller, params):
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    payload = {
        "session": session,
        "controller": controller,
        "params": params
    }
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=15)
        print(f"\n[{controller}] Status: {res.status_code}")
        body = res.json()
        print(f"[{controller}] Keys: {list(body.keys())}")
        if "error" in body:
            print(f"[{controller}] Error: {body['error']}")
        else:
            # Print a snippet of the result
            print(f"[{controller}] Result Snippet: {json.dumps(body, indent=2, ensure_ascii=False)[:1500]}")
    except Exception as e:
        print(f"[{controller}] Failed: {e}")

def main():
    url, email, password = load_credentials()
    if not url:
        print("Credentials not found.")
        sys.exit(1)
        
    # Read saved session
    with open(TOKEN_FILE, "r") as f:
        data = json.load(f)
        session = data.get("croco_session")
        
    print(f"Using saved session: {session}")
    
    # 2026-06-04 UTC boundaries
    # start_ts is 2026-06-04 00:00:00 UTC
    start_ts = 1780531200
    end_ts = 1780617600
    
    # Let's test tracks_by_days with different parameters
    test_controller(url, session, "tracks_by_days", {
        "interval": [start_ts, end_ts]
    })
    
    test_controller(url, session, "active_track", {
        "interval": [start_ts, end_ts]
    })
    
    test_controller(url, session, "timesheet_report", {
        "interval": [start_ts, end_ts],
        "view": 2, # LIST
        "type": 0, # ACTIVITY
        "write_empty": 1
    })

if __name__ == "__main__":
    main()
