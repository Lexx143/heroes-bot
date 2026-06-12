import requests
import re

url = "http://192.168.102.22:8085/_build/crocojs_pkg_base_9eb5da2904f502ac3428ad72f9a2f603.js"
print("Downloading base JS file...")
res = requests.get(url, timeout=15)
if res.status_code == 200:
    content = res.text
    # Find all occurrences of WORKED_OUT
    pos = 0
    while True:
        pos = content.find("WORKED_OUT", pos)
        if pos == -1:
            break
        print(f"Found WORKED_OUT in base JS at {pos}. Snippet:")
        print(content[pos-100:pos+300])
        pos += len("WORKED_OUT")
        
    print("\nChecking croco JS...")
    url_croco = "http://192.168.102.22:8085/_build/crocojs_pkg_croco_9eb5da2904f502ac3428ad72f9a2f603.js"
    res_croco = requests.get(url_croco, timeout=15)
    if res_croco.status_code == 200:
        content_croco = res_croco.text
        pos = 0
        while True:
            pos = content_croco.find("WORKED_OUT", pos)
            if pos == -1:
                break
            print(f"Found WORKED_OUT in croco JS at {pos}. Snippet:")
            print(content_croco[pos-100:pos+300])
            pos += len("WORKED_OUT")
else:
    print("Download failed.")
