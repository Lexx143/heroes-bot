import requests

url = "http://192.168.102.22:8085/_build/crocojs_pkg_croco_9eb5da2904f502ac3428ad72f9a2f603.js"
print("Downloading JS file...")
res = requests.get(url, timeout=15)
if res.status_code == 200:
    content = res.text
    pos = content.find("COLUMNS_SERVER_VALUES")
    if pos != -1:
        print(f"Found in croco JS at {pos}. Snippet:")
        print(content[pos-100:pos+1000])
    else:
        print("Not found in croco JS. Checking base JS...")
        url_base = "http://192.168.102.22:8085/_build/crocojs_pkg_base_9eb5da2904f502ac3428ad72f9a2f603.js"
        res_base = requests.get(url_base, timeout=15)
        if res_base.status_code == 200:
            content_base = res_base.text
            pos_base = content_base.find("COLUMNS_SERVER_VALUES")
            if pos_base != -1:
                print(f"Found in base JS at {pos_base}. Snippet:")
                print(content_base[pos_base-100:pos_base+1000])
            else:
                print("Not found in base JS either.")
else:
    print("Download failed.")
