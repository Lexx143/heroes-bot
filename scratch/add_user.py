import os
import sys
import gspread
from google.oauth2.service_account import Credentials

def main():
    creds_file = "../google_creds.json"
    sheet_title = "hadsome_stat"
    
    if not os.path.exists(creds_file):
        creds_file = "google_creds.json"
        
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_file(creds_file, scopes=scopes)
    gc = gspread.authorize(creds)
    
    try:
        sh = gc.open(sheet_title)
        ws = sh.worksheet("Сотрудники")
        # Append row: ФИО, Telegram Username, Telegram User ID, Есть CrocoTime, Croco ID, CRM ID, Время начала, Запрашивать план, Текущая ачивка, Дней подряд
        ws.append_row([
            "Alexx (Администратор)", "DeusLexx", "226959621", "Нет", "", "", "11:00:00", "Да", "", "0"
        ])
        print("Successfully added DeusLexx to the spreadsheet!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
