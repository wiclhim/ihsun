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
assert len(home["list"]) == channel.PAGE_SIZE
assert len(home["class"]) == len(channel.CATEGORIES)
first_page = channel.categoryContent("all", 1, False, {})
second_page = channel.categoryContent("all", 2, False, {})
assert first_page["pagecount"] >= 2
assert len(first_page["list"]) == channel.PAGE_SIZE
assert set(item["vod_id"] for item in first_page["list"]).isdisjoint(
    item["vod_id"] for item in second_page["list"])
categories = {}
category_first = {}
for category in ("ai-duanju", "ai-manju", "original", "original-duanju",
                 "original-manju", "rank-hot", "rank-recommend", "rank-potential",
                 "favorites"):
    result = channel.categoryContent(category, 1, False, {})
    assert result["list"]
    categories[category] = (len(result["list"]), result["total"])
    category_first[category] = result["list"][0]["vod_id"]
search = channel.searchContent("神瞳", False, "1")
assert search["list"] and search["total"] >= len(search["list"])
search_page_one = channel.searchContent("神", False, "1")
search_page_two = channel.searchContent("神", False, "2")
assert search_page_one["pagecount"] >= 2
assert set(item["vod_id"] for item in search_page_one["list"]).isdisjoint(
    item["vod_id"] for item in search_page_two["list"])
detail = channel.detailContent(["15372"])["list"][0]
multi = channel.detailContent(["117"])["list"][0]
assert len(multi["vod_play_url"].split("#")) == 48
multi_play = channel.playerContent("", multi["vod_play_url"].split("#")[1].split("$", 1)[1], [])
assert multi_play["url"].startswith("https://")
multi_manifest = requests.get(multi_play["url"], headers=multi_play["header"], timeout=15)
multi_manifest.raise_for_status()
assert multi_manifest.text.startswith("#EXTM3U")
comic = channel.detailContent([category_first["ai-manju"]])["list"][0]
comic_play = channel.playerContent("", comic["vod_play_url"].split("#")[0].split("$", 1)[1], [])
comic_manifest = requests.get(comic_play["url"], headers=comic_play["header"], timeout=15)
comic_manifest.raise_for_status()
assert comic_manifest.text.startswith("#EXTM3U")
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
    "all_total": first_page["total"],
    "categories": categories,
    "search_count": len(search["list"]),
    "search_page_two_count": len(search_page_two["list"]),
    "episode_count": len(detail["vod_play_url"].split("#")),
    "multi_episode_count": len(multi["vod_play_url"].split("#")),
    "multi_manifest_status": multi_manifest.status_code,
    "comic_manifest_status": comic_manifest.status_code,
    "manifest_status": manifest.status_code,
    "manifest_hls": manifest.text.startswith("#EXTM3U"),
    "resource_statuses": statuses,
}, ensure_ascii=True))
