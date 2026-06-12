import requests
import re

url = "http://192.168.102.22:8085/_build/crocojs_pkg_base_9eb5da2904f502ac3428ad72f9a2f603.js"
print("Downloading JS file...")
res = requests.get(url, timeout=15)
if res.status_code == 200:
    content = res.text
    
    # Search for visible_columns occurrences
    pos = 0
    while True:
        pos = content.find("visible_columns", pos)
        if pos == -1:
            break
        print(f"Found visible_columns at {pos}. Snippet:")
        print(content[pos-200:pos+300])
        pos += len("visible_columns")
else:
    print("Download failed.")
