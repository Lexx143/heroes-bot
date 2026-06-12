import requests
import re

url = "http://192.168.102.22:8085/"
js_files = [
    "_build/crocojs_pkg_base_9eb5da2904f502ac3428ad72f9a2f603.js",
    "_build/crocojs_pkg_croco_9eb5da2904f502ac3428ad72f9a2f603.js",
    "_build/final_9eb5da2904f502ac3428ad72f9a2f603.js"
]

for js_file in js_files:
    file_url = f"{url}{js_file}"
    print(f"Scanning {file_url}...")
    try:
        res = requests.get(file_url, timeout=15)
        if res.status_code == 200:
            content = res.text
            for pattern in ["Block.V.prototype.ja", "Block.V =", "Block.V=function"]:
                pos = content.find(pattern)
                if pos != -1:
                    print(f"  Found '{pattern}' in {js_file} at {pos}. Snippet:")
                    print(content[pos:pos+1000])
                    break
    except Exception as e:
        print(f"  Failed: {e}")
