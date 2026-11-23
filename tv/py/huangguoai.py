# -*- coding: utf-8 -*-
"""Huangguo catalog and playback for the TVBox Python Spider interface."""

import json
import re

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    HOST = "https://huangguoai.com"
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    PAGE_SIZE = 20
    CATEGORIES = (
        ("all", "全部短劇"),
        ("ai-duanju", "AI短劇"),
        ("ai-manju", "AI漫劇"),
        ("original", "黃果原創"),
        ("original-duanju", "原創短劇"),
        ("original-manju", "原創漫劇"),
        ("rank-hot", "熱播排行"),
        ("rank-recommend", "推薦排行"),
        ("rank-potential", "潛力排行"),
        ("favorites", "我的收藏"),
    )

    def __init__(self):
        self.video_ids = []
        self._cover_urls = {}
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.UA,
            "Accept": "application/json",
            "Referer": self.HOST + "/",
        })
        retry = Retry(total=2, backoff_factor=0.4,
                      status_forcelist=[429, 500, 502, 503, 504])
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def init(self, extend=""):
        config = json.loads(extend) if isinstance(extend, str) and extend else (extend or {})
        ids = config.get("video_ids", []) if isinstance(config, dict) else []
        self.video_ids = [str(value) for value in ids if re.fullmatch(r"\d+", str(value))]

    def getName(self):
        return "huangguoai 黃果短劇"

    def homeContent(self, filter):
        return {"class": [{"type_id": key, "type_name": name} for key, name in self.CATEGORIES],
                "list": self.homeVideoContent()["list"]}

    def homeVideoContent(self):
        data = self._api("GET", "/api/videos", {"page": 1, "size": self.PAGE_SIZE})
        return {"list": [self._vod(item) for item in data.get("items", [])]}

    def categoryContent(self, tid, pg, filter, extend):
        page = max(1, int(pg))
        if tid == "favorites":
            items = [self._summary(video_id) for video_id in self.video_ids] if page == 1 else []
            return {"page": page, "pagecount": 1, "limit": max(1, len(self.video_ids)),
                    "total": len(self.video_ids), "list": items}
        if tid.startswith("rank-"):
            if page > 1:
                return self._page([], page, {"pages": 1, "total": 20})
            kind = tid[5:]
            if kind not in ("hot", "recommend", "potential"):
                raise ValueError("未知的排行分類")
            data = self._api("GET", "/api/ranks/" + kind)
            return self._page(data.get("items", []), page, {"pages": 1, "total": len(data.get("items", []))})
        if tid not in {key for key, _ in self.CATEGORIES}:
            raise ValueError("未知的影片分類")
        params = {"page": page, "size": self.PAGE_SIZE}
        if tid == "ai-duanju":
            params["cate_id"] = 24
        elif tid == "ai-manju":
            params["cate_id"] = 25
        elif tid == "original":
            params["is_original"] = 1
        elif tid == "original-duanju":
            params.update({"is_original": 1, "cate_id": 24})
        elif tid == "original-manju":
            params.update({"is_original": 1, "cate_id": 25})
        data = self._api("GET", "/api/videos", params)
        return self._page(data.get("items", []), page, data.get("pagination", {}))

    def detailContent(self, ids):
        video_id = self._video_id(ids[0])
        data = self._api("GET", "/api/videos/" + video_id)
        episodes = data.get("episodes") or []
        if not episodes and data.get("episode_count"):
            episodes = [{"ep_num": number} for number in range(1, int(data["episode_count"]) + 1)]
        play = []
        for episode in episodes:
            number = int(episode.get("ep_num") or 0)
            if number < 1 or str(episode.get("status", 1)) != "1":
                continue
            label = str(episode.get("title") or "第%d集" % number).replace("#", " ").replace("$", " ")
            play.append("%s$%s:%d" % (label, video_id, number))
        return {"list": [{
            "vod_id": video_id,
            "vod_name": data.get("title") or video_id,
            "vod_pic": self._cover(video_id, data.get("cover")),
            "vod_content": data.get("description") or "",
            "vod_remarks": "更新至%d集" % len(play),
            "vod_play_from": "黃果短劇",
            "vod_play_url": "#".join(play),
        }]}

    def playerContent(self, flag, id, vipFlags):
        video_id, separator, episode = str(id).partition(":")
        self._video_id(video_id)
        if not separator or not re.fullmatch(r"[1-9]\d*", episode):
            raise ValueError("無效的集數識別碼")
        data = self._api("POST", "/api/videos/%s/episodes/%s/playback" % (video_id, episode))
        url = (data.get("streams") or {}).get("main")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise ValueError("播放 API 未提供有效的 HLS 來源")
        header = {"User-Agent": self.UA, "Referer": self.HOST + "/"}
        cdn = data.get("cdn") or {}
        if cdn.get("authKey") and cdn.get("authValue"):
            header[str(cdn["authKey"])] = str(cdn["authValue"])
        return {"parse": 0, "playUrl": "", "url": url, "header": header}

    def localProxy(self, param):
        if param.get("type") != "cover":
            return [404, "text/plain", b"not found"]
        try:
            video_id = self._video_id(param.get("id"))
            url = self._cover_urls.get(video_id)
            if not url:
                url = self._api("GET", "/api/videos/" + video_id).get("cover")
            for attempt in range(2):
                if not isinstance(url, str) or not url.startswith("https://"):
                    raise ValueError("沒有可用的封面網址")
                response = self.session.get(url, timeout=15)
                if response.status_code in (401, 403, 404, 410) and attempt == 0:
                    url = self._api("GET", "/api/videos/" + video_id).get("cover")
                    self._cover_urls[video_id] = url
                    continue
                response.raise_for_status()
                if not response.content or len(response.content) > 8 * 1024 * 1024:
                    raise ValueError("封面資料大小異常")
                mime, image = self._decode_cover(response.content)
                return [200, mime, image, {"Content-Length": str(len(image))}]
        except ImportError:
            return [503, "text/plain", b"AES support unavailable"]
        except Exception:
            return [502, "text/plain", b"cover unavailable"]
        return [502, "text/plain", b"cover unavailable"]

    def searchContent(self, key, quick, pg="1"):
        if not str(key).strip():
            return self._page([], max(1, int(pg)), {"pages": 1, "total": 0})
        page = max(1, int(pg))
        data = self._api("GET", "/api/search",
                         {"q": str(key).strip(), "page": page, "size": self.PAGE_SIZE})
        return self._page(data.get("items", []), page, data.get("pagination", {}))

    def _summary(self, video_id):
        data = self._api("GET", "/api/videos/" + self._video_id(video_id))
        return self._vod(data)

    def _vod(self, data):
        video_id = str(data.get("id") or data.get("video_id") or "")
        self._video_id(video_id)
        count = data.get("episode_count") or 0
        return {"vod_id": video_id, "vod_name": data.get("title") or video_id,
                "vod_pic": self._cover(video_id, data.get("cover")),
                "vod_remarks": "更新至%s集" % count}

    def _cover(self, video_id, url):
        if url:
            self._cover_urls[video_id] = url
        return self.getProxyUrl() + "&type=cover&id=" + video_id

    @staticmethod
    def _decode_cover(content):
        def image_type(data):
            if data.startswith(b"\xff\xd8\xff"):
                return "image/jpeg"
            if data.startswith(b"\x89PNG\r\n\x1a\n"):
                return "image/png"
            if data.startswith((b"GIF87a", b"GIF89a")):
                return "image/gif"
            if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
                return "image/webp"
            return ""

        plain_type = image_type(content)
        if plain_type:
            return plain_type, content
        key = b"f5d965df75336270"
        iv = b"97b60394abc2fbe1"
        padded = content + b"\0" * (-len(content) % 16)
        try:
            from Crypto.Cipher import AES
            decoded = AES.new(key, AES.MODE_CBC, iv).decrypt(padded)
        except ImportError:
            try:
                from Cryptodome.Cipher import AES
                decoded = AES.new(key, AES.MODE_CBC, iv).decrypt(padded)
            except ImportError:
                from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
                decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
                decoded = decryptor.update(padded) + decryptor.finalize()
        decoded = decoded[:len(content)]
        mime = image_type(decoded)
        if not mime:
            raise ValueError("封面解密後不是可辨識的圖片")
        return mime, decoded

    def _page(self, items, page, pagination):
        return {"page": page,
                "pagecount": max(1, int(pagination.get("pages") or 1)),
                "limit": int(pagination.get("size") or self.PAGE_SIZE),
                "total": int(pagination.get("total") or 0),
                "list": [self._vod(item) for item in items]}

    def _api(self, method, path, params=None):
        response = self.session.request(method, self.HOST + path,
                                        params=params,
                                        json={} if method == "POST" else None, timeout=12)
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != 1 or not isinstance(payload.get("data"), dict):
            raise ValueError("網站 API 錯誤：%s" % (payload.get("msg") or "無有效資料"))
        return payload["data"]

    @staticmethod
    def _video_id(value):
        value = str(value)
        if not re.fullmatch(r"\d+", value):
            raise ValueError("無效的影片識別碼")
        return value
