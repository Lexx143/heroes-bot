import requests

url = "http://192.168.102.22:8085/_build/crocojs_pkg_croco_9eb5da2904f502ac3428ad72f9a2f603.js"
print("Downloading JS file...")
res = requests.get(url, timeout=15)
if res.status_code == 200:
    content = res.text
    pos = content.find("Block.ViewTracks=")
    if pos == -1:
        pos = content.find("Block.ViewTracks =")
    if pos != -1:
        print(f"Found Block.ViewTracks at {pos}. Extracting 2000 chars:")
        print(content[pos:pos+2000])
        
        # Let's search from pos onwards for "a.filterGroups" or "a.defaultColumns" or "a.columns"
        # because the initializer typically sets these
        pos_init = content.find(".a=function", pos, pos+10000)
        if pos_init != -1:
            print(f"Found .a=function (initializer) at {pos_init}. Extracting 2000 chars:")
            print(content[pos_init:pos_init+2000])
    else:
        print("Not found Block.ViewTracks.")
else:
    print("Download failed.")
