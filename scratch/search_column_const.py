import requests
import re

url = "http://192.168.102.22:8085/_build/crocojs_pkg_base_9eb5da2904f502ac3428ad72f9a2f603.js"
print("Downloading base JS file...")
res = requests.get(url, timeout=15)
if res.status_code == 200:
    content = res.text
    
    # Try searching for Const.Column or Column enum definition
    for pattern in [r"Const\.Column\b", r"\bColumn\b\s*=", r"\bColumn\b\s*:"]:
        matches = list(re.finditer(pattern, content))
        if matches:
            print(f"\nMatches for pattern '{pattern}':")
            for idx, m in enumerate(matches[:5]):
                start = max(0, m.start() - 150)
                end = min(len(content), m.end() + 300)
                print(f"  Match {idx+1}:\n{content[start:end]}\n")
else:
    print("Download failed.")
