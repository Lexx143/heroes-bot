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
            for term in ["tracks_by_days", "active_track", "incidents_detail"]:
                matches = list(re.finditer(re.escape(term), content))
                if matches:
                    print(f"  Found {len(matches)} matches for '{term}':")
                    for idx, m in enumerate(matches[:10]):
                        start = max(0, m.start() - 300)
                        end = min(len(content), m.end() + 300)
                        print(f"    Match {idx+1} in {js_file} around {m.start()}:\n{content[start:end]}\n")
    except Exception as e:
        print(f"  Failed: {e}")
