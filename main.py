import os
import sys
import asyncio
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ChatMemberHandler,
    CallbackQueryHandler
)
import config
import bot
import scheduler
from sheets import SheetsClient
from croco import CrocoClient
from team_client import init_team_client
from crm import CRMClient

background_tasks = set()

async def post_init(application):
    # Start the async scheduler loop in the background of the main asyncio loop
    task = asyncio.create_task(scheduler.scheduler_loop(application))
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
    print("[Main] Scheduler task spawned in event loop.")

def main():
    print("--- Workday Monitoring Bot Starting ---")
    
    # 1. Initialize Google Sheets Client
    try:
        sheets_client = SheetsClient(
            creds_file=config.GOOGLE_CREDENTIALS_FILE,
            sheet_title=config.GOOGLE_SHEET_TITLE,
            share_email=config.SHARE_USER_EMAIL
        )
    except FileNotFoundError as e:
        print("\n" + "!"*80)
        print("GOOGLE CREDENTIALS FILE MISSING:")
        print(str(e))
        print("\nINSTRUCTIONS:")
        print("1. Go to Google Cloud Console.")
        print("2. Create a Service Account and download its JSON private key file.")
        print("3. Rename the JSON file to 'google_creds.json' and place it in this directory.")
        print("4. Restart the bot.")
        print("!"*80 + "\n")
        sys.exit(1)
    except Exception as e:
        print(f"[Main] Failed to initialize Google Sheets client: {e}")
        sys.exit(1)

    # 2. Initialize CrocoTime Client
    croco_client = CrocoClient(
        base_url=config.CROCO_URL,
        email=config.CROCO_LOGIN,
        password=config.CROCO_PASSWORD,
        token_file=config.TOKEN_STORE_FILE
    )
    
    # Initialize Team Client
    team_client = init_team_client(
        config.CROCO_LOGIN,
        config.CROCO_PASSWORD
    )
    team_client.login()

    # 3. Initialize Asista CRM Client
    crm_client = CRMClient(
        token_file=config.TOKEN_STORE_FILE
    )

    # 4. Inject dependencies
    bot.sheets_client = sheets_client
    bot.crm_client = crm_client
    bot.team_client = team_client
    
    scheduler.crm_client = crm_client
    scheduler.croco_client = croco_client
    scheduler.team_client = team_client
    scheduler.sheets_client = sheets_client

    # 5. Build Telegram Application
    token = config.TELEGRAM_BOT_TOKEN
    if not token:
        print("[Main] Error: TELEGRAM_BOT_TOKEN is not set.")
        sys.exit(1)

    print(f"[Main] Initializing Telegram Bot with token prefix: {token.split(':')[0]}")
    
    application = (
        ApplicationBuilder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    # 6. Register Handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CallbackQueryHandler(bot.handle_register_callback, pattern='^reg_'))
    application.add_handler(CommandHandler("register", bot.register))
    application.add_handler(CommandHandler("setgroup", bot.set_group))
    application.add_handler(CommandHandler("sync", bot.sync_members))
    
    # Handle geoposition location check-ins
    application.add_handler(MessageHandler(filters.LOCATION, bot.location_handler))
    
    # Handle text messages in private chats (daily CRM task plans / statuses)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, bot.text_handler))
    
    # Handle voice messages in private chats (daily CRM task plans via voice)
    application.add_handler(MessageHandler(filters.VOICE & filters.ChatType.PRIVATE, bot.voice_handler))
    
    # Handle text messages in group chats (auto-register members when they type)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS, bot.group_message_handler))
    
    # Handle chat member updates (join/leave)
    application.add_handler(ChatMemberHandler(bot.chat_member_handler, ChatMemberHandler.CHAT_MEMBER))

    # 7. Start polling (blocking call)
    print("[Main] Bot is now polling for updates. Press Ctrl+C to exit.")
    application.run_polling()

if __name__ == "__main__":
    main()
