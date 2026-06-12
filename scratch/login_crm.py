import time
import json
import os
from playwright.sync_api import sync_playwright

token_file = "/Users/lexx/coding/projects/deus_bot/scratch/token_store.json"

def run():
    print("Launching Chromium in headless mode...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            service_workers='block',
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()

        print("Navigating to https://crm.asista.kz/applications...")
        page.goto("https://crm.asista.kz/applications")

        # Wait for page elements to load
        time.sleep(5)
        print(f"Current page URL: {page.url}")

        # Autofill
        username_filled = False
        password_filled = False
        
        for selector in ["input[type='text']", "input[name='username']", "input[placeholder*='Логин']", "input[placeholder*='логин']"]:
            if page.locator(selector).is_visible():
                page.fill(selector, "IT162")
                username_filled = True
                break
        
        for selector in ["input[type='password']", "input[name='password']", "input[placeholder*='Пароль']", "input[placeholder*='пароль']"]:
            if page.locator(selector).is_visible():
                page.fill(selector, "X_z92032")
                password_filled = True
                break

        print(f"Autofill status - Username filled: {username_filled}, Password filled: {password_filled}")

        if not (username_filled and password_filled):
            print("Error: Could not locate login fields.")
            browser.close()
            return

        # Click submit button or press Enter
        button_clicked = False
        for btn_selector in ["button[type='submit']", "button:has-text('Войти')", "button:has-text('Sign in')", "input[type='submit']"]:
            if page.locator(btn_selector).is_visible():
                page.click(btn_selector)
                print(f"Clicked login button using selector: {btn_selector}")
                button_clicked = True
                break
        
        if not button_clicked:
            print("Submit button not found. Pressing Enter on password field...")
            page.press("input[type='password']", "Enter")

        # Wait for navigation/redirection
        print("Waiting for redirection...")
        time.sleep(10)
        print(f"Current page URL after login: {page.url}")

        cookies = context.cookies()
        refresh_token = None
        for cookie in cookies:
            if cookie.get("name") == "refresh_token":
                refresh_token = cookie.get("value")
                break

        if refresh_token:
            print("Successfully retrieved refresh_token cookie!")
            
            # Load existing config
            data = {}
            if os.path.exists(token_file):
                try:
                    with open(token_file, "r") as f:
                        data = json.load(f)
                except Exception:
                    pass
            
            # Update refresh token
            data["refresh_token"] = refresh_token
            
            # Write back
            with open(token_file, "w") as f:
                json.dump(data, f, indent=4)
                
            print(f"Token store updated successfully at '{token_file}'")
        else:
            print("Error: refresh_token cookie not found. Cookies retrieved:")
            for c in cookies:
                print(f"  {c.get('name')}: {c.get('domain')}")
                
        browser.close()

if __name__ == "__main__":
    run()
