import importlib.util
import json
import re
import sys
import types
from urllib.parse import urljoin

import json5
import requests

base = types.ModuleType("base")
spider = types.ModuleType("base.spider")
spider.Spider = type("Spider", (), {})
sys.modules["base"] = base
sys.modules["base.spider"] = spider
spec = importlib.util.spec_from_file_location("huangguoai", "tv/py/huangguoai.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

with open("tvbox18.json", encoding="utf-8") as handle:
    config = json5.load(handle)
entry = next(site for site in config["sites"] if site["key"] == "huangguoai-single-py")
channel = module.Spider()
channel.init(entry["ext"])
assert "huangguoai" in entry["name"]
assert channel.getName() == entry["name"].removesuffix("[py]")
home = channel.homeContent(False)
detail = channel.detailContent(["15372"])["list"][0]
play_id = detail["vod_play_url"].split("$", 1)[1]
play = channel.playerContent("", play_id, [])
manifest = requests.get(play["url"], headers=play["header"], timeout=15)
manifest.raise_for_status()
assert manifest.text.startswith("#EXTM3U")
key = re.search(r'#EXT-X-KEY:[^\n]*URI="([^"]+)"', manifest.text)
segment = next((line for line in manifest.text.splitlines() if line and not line.startswith("#")), None)
statuses = {}
for label, uri in (("key", key.group(1) if key else None), ("segment", segment)):
    if uri:
        with requests.get(urljoin(play["url"], uri), headers=play["header"],
                          timeout=15, stream=True) as response:
            statuses[label] = response.status_code

print(json.dumps({
    "home_count": len(home["list"]),
    "episode_count": len(detail["vod_play_url"].split("#")),
    "manifest_status": manifest.status_code,
    "manifest_hls": manifest.text.startswith("#EXTM3U"),
    "resource_statuses": statuses,
}, ensure_ascii=True))
