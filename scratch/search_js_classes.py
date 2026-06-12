import requests
import re

url = "http://192.168.102.22:8085/_build/crocojs_pkg_croco_9eb5da2904f502ac3428ad72f9a2f603.js"
print("Downloading JS file...")
res = requests.get(url, timeout=15)
if res.status_code == 200:
    content = res.text
    
    # 1. Search for .Rl definition
    pos_rl = content.find(".Rl=function")
    if pos_rl == -1:
        pos_rl = content.find("Rl:function")
    if pos_rl != -1:
        print(f"\nFound .Rl definition around {pos_rl}:")
        print(content[pos_rl - 50:pos_rl + 1000])
        
    # 2. Search for Block.V.prototype.ja
    pos_vja = content.find("Block.V.prototype.ja")
    if pos_vja != -1:
        print(f"\nFound Block.V.prototype.ja around {pos_vja}:")
        print(content[pos_vja - 50:pos_vja + 1000])
        
    # 3. Search for tracksByDays class name or structure
    pos_tbd = content.find("tracksByDays")
    if pos_tbd != -1:
        print(f"\nFound tracksByDays around {pos_tbd}:")
        print(content[pos_tbd - 100:pos_tbd + 1000])
else:
    print("Download failed.")
