import os
import json
import requests

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
    
    # List of column candidates to test
    candidates = [
        "SUMMARY", "PERMITTED", "FORBIDDEN", "NON_COMPUTER", "HOLIDAY",
        "LATE_COUNT", "EARLY_END_COUNT", "ABSENCES", "NORM", "DIFF",
        "WORK_BEGIN", "WORK_END", "WORKED_OUT", "PLAIN_SUMMARY"
    ]
    
    for c in candidates:
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
                                "visible_columns": [c]
                            },
                            "write_empty": 1,
                            "view": 1,
                            "type": 0
                        },
                        "subsystems": [{"uuid": "com.infomaximum.crocotime", "app_version": "5.8.11"}],
                        "app_version": "5.8.11"
                    }
                ]
            },
            "app_version": "5.8.11"
        }
        res = requests.post(url, json=payload, headers=headers, cookies=cookies, timeout=10)
        body = res.json()
        report_result = body.get("result", {}).get("TimeSheetWorkTime", {})
        if "error" in report_result:
            print(f"Column '{c}': REJECTED ({report_result['error']['message']})")
        else:
            print(f"Column '{c}': ACCEPTED!")
            # Print a sample day item to see what data fields it returned
            items = report_result.get("result", {}).get("root", {}).get("items", [])
            for item in items:
                days = item.get("days", [])
                if days:
                    print(f"  Sample day data: {days[0]}")
                    break

if __name__ == "__main__":
    main()
