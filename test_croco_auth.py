import config
from croco import CrocoClient

client = CrocoClient(config.CROCO_URL, config.CROCO_LOGIN, config.CROCO_PASSWORD, config.TOKEN_STORE_FILE)

import requests, hashlib
md5_password = hashlib.md5(client.password.encode('utf-8')).hexdigest()
payload = {
    "name": "Logon",
    "controller": "LogonController",
    "params": {
        "user": {
            "login": client.email,
            "password": md5_password
        }
    }
}
headers = {"Content-Type": "application/json; charset=utf-8", "user-agent": "Mozilla/5.0"}
res = requests.post(client.base_url, json=payload, headers=headers)
print(res.status_code)
print(res.text)

