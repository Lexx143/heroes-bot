import requests

url = "http://192.168.102.22:8085/_build/crocojs_pkg_base_9eb5da2904f502ac3428ad72f9a2f603.js"
print("Downloading base JS file...")
res = requests.get(url, timeout=15)
if res.status_code == 200:
    content = res.text
    # Find Block.V prototype definition
    pos_v = content.find("Block.V=function")
    # Let's search from pos_v onwards for ".ja=function" or "ja:function"
    pos_ja = content.find(".ja=function", pos_v)
    if pos_ja != -1 and pos_ja - pos_v < 100000: # Make sure it belongs to Block.V or close prototypes
        print(f"Found .ja=function on prototype near Block.V at {pos_ja}. Extracting 2000 chars:")
        print(content[pos_ja:pos_ja+2000])
    else:
        # Search anywhere in base JS
        pos_ja_any = content.find("Block.V.prototype.ja")
        if pos_ja_any != -1:
            print(f"Found Block.V.prototype.ja at {pos_ja_any}. Extracting:")
            print(content[pos_ja_any:pos_ja_any+2000])
        else:
            print("Not found.")
else:
    print("Download failed.")
