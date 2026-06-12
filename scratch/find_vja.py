import requests

url = "http://192.168.102.22:8085/_build/crocojs_pkg_croco_9eb5da2904f502ac3428ad72f9a2f603.js"
print("Downloading JS file...")
res = requests.get(url, timeout=15)
if res.status_code == 200:
    content = res.text
    pos = content.find("Block.V.prototype.ja=function")
    if pos == -1:
        pos = content.find("Block.V.prototype.ja = function")
    if pos == -1:
        pos = content.find("Block.V.prototype.ja=")
    if pos != -1:
        print(f"Found Block.V.prototype.ja at {pos}. Extracting 2000 chars:")
        print(content[pos:pos+2000])
    else:
        print("Not found.")
else:
    print("Download failed.")
