import config
from croco import CrocoClient
from datetime import datetime

client = CrocoClient(config.CROCO_URL, config.CROCO_LOGIN, config.CROCO_PASSWORD, config.TOKEN_STORE_FILE)
today_str = datetime.now().strftime("%Y-%m-%d")
print("Start times:", client.get_work_start_times(today_str))

