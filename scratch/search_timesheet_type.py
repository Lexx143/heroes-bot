import requests
import re

url = "http://192.168.102.22:8085/_build/crocojs_pkg_croco_9eb5da2904f502ac3428ad72f9a2f603.js"
print("Downloading JS file...")
res = requests.get(url, timeout=15)
if res.status_code == 200:
    content = res.text
    pos = 0
    while True:
        pos = content.find("TIME_SHEET_TYPE", pos)
        if pos == -1:
            break
        print(f"Found TIME_SHEET_TYPE at {pos}. Snippet:")
        print(content[pos-100:pos+300])
        pos += len("TIME_SHEET_TYPE")
else:
    print("Download failed.")
