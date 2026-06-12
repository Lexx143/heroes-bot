import os
import json
import requests
from datetime import datetime, timezone

TOKEN_FILE = "/Users/lexx/coding/projects/deus_bot/scratch/token_store.json"

def main():
    with open(TOKEN_FILE, "r") as f:
        data = json.load(f)
        url = data.get("croco_url")
        session = data.get("croco_session")
        
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    cookies = {"session": session}
    
    start_ts = 1780531200
    end_ts = 1780617600
    
    # Let's try different BatchProcessing queries
    queries = {
        "tracks_by_days": {
            "name": "TracksByDays",
            "controller": "tracks_by_days",
            "params": {
                "interval": [start_ts, end_ts],
                "columns": {
                    "visible_columns": ["PERSON", "PROJECT", "TASK_TYPE", "RESULT", "TIME_BEGIN", "TIME_END", "WORKING_TIME"]
                },
                "employee_filter": {
                    "main_employee_filter": {
                        "selected_items": [677, 1291, 77, 1181],
                        "selected_groups": []
                    }
                }
            },
            "subsystems": [{"uuid": "com.infomaximum.crocotime", "app_version": "5.8.11"}],
            "app_version": "5.8.11"
        },
        "day_departments_detalization": {
            "name": "DayDepartmentsDetalization",
            "controller": "day_departments_detalization",
            "params": {
                "interval": [start_ts, end_ts]
            },
            "subsystems": [{"uuid": "com.infomaximum.crocotime", "app_version": "5.8.11"}],
            "app_version": "5.8.11"
        },
        "active_track": {
            "name": "ActiveTrack",
            "controller": "active_track",
            "params": {
                "interval": [start_ts, end_ts]
            },
            "subsystems": [{"uuid": "com.infomaximum.crocotime", "app_version": "5.8.11"}],
            "app_version": "5.8.11"
        }
    }
    
    for q_name, q_item in queries.items():
        payload = {
            "controller": "BatchProcessing",
            "revalidate_hash": "9eb5da2904f502ac3428ad72f9a2f603",
            "query": {
                "items": [q_item]
            },
            "app_version": "5.8.11"
        }
        try:
            print(f"\n--- Querying {q_name} via BatchProcessing ---")
            res = requests.post(url, json=payload, headers=headers, cookies=cookies, timeout=15)
            print(f"Status: {res.status_code}")
            body = res.json()
            result_data = body.get("result", {})
            print(f"Result keys: {list(result_data.keys())}")
            
            # Print result data sample
            snippet = json.dumps(result_data, indent=2, ensure_ascii=False)
            print(snippet[:1500])
            if len(snippet) > 1500:
                print("... [TRUNCATED]")
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == "__main__":
    main()
