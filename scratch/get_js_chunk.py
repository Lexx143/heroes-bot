import requests

url = "http://192.168.102.22:8085/_build/crocojs_pkg_croco_9eb5da2904f502ac3428ad72f9a2f603.js"
print(f"Downloading JS file...")
res = requests.get(url, timeout=15)
if res.status_code == 200:
    content = res.text
    pos = content.find("tracks_by_days")
    if pos != -1:
        print(f"Found tracks_by_days at {pos}. Extracting from {pos - 100} to {pos + 2000}:")
        print(content[pos - 100:pos + 2000])
    else:
        print("Not found.")
