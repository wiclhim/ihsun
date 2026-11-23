# -*- coding: utf-8 -*-
"""MissAV public pages for TVBox / OK影視."""
import re
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        pass


class Spider(BaseSpider):
    HOSTS = ("https://missav.live", "https://missav123.com", "https://missav.ws")
    CATEGORIES = (
        ("new", "最近更新"),
        ("release", "新作上市"),
        ("chinese-subtitle", "中文字幕"),
        ("today-hot", "今日熱門"),
        ("weekly-hot", "本週熱門"),
        ("monthly-hot", "本月熱門"),
        ("uncensored-leak", "無碼流出"),
        ("fc2", "無碼・FC2"),
    )
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    }

    def __init__(self):
        super().__init__()
        self.host = self.HOSTS[0]
        self.last_error = ""
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def init(self, extend="{}"):
        return None

    def getName(self):
        return "MissAV"

    def homeContent(self, filter):
        items = self._list(self._get("/new"))
        return {"class": [{"type_id": path, "type_name": name} for path, name in self.CATEGORIES],
                "filters": {}, "list": items or [self._diagnostic()], "parse": 0, "jx": 0}

    def homeVideoContent(self):
        return {"list": self._list(self._get("/new")) or [self._diagnostic()]}

    def categoryContent(self, tid, pg, filter, extend):
        page = self._page(pg)
        path = str(tid or "new").strip("/")
        if path not in dict(self.CATEGORIES):
            return self._paged([], page)
        return self._paged(self._list(self._get("/" + path, {"page": page})) or [self._diagnostic()], page)

    def searchContent(self, key, quick, pg="1"):
        page = self._page(pg)
        if not str(key or "").strip():
            return self._paged([], page)
        return self._paged(self._list(self._get("/search/" + quote(str(key).strip()), {"page": page})) or [self._diagnostic()], page)

    def detailContent(self, ids):
        if not ids:
            return {"list": [], "parse": 0, "jx": 0}
        if ids[0] == "__missav_error__":
            return {"list": [{"vod_id": ids[0], "vod_name": "MissAV 連線狀態", "vod_content": self.last_error or "未取得影片清單", "vod_play_from": "", "vod_play_url": ""}], "parse": 0, "jx": 0}
        path = self._path(ids[0])
        html = self._get(path)
        if not html:
            return {"list": [], "parse": 0, "jx": 0}
        soup = BeautifulSoup(html, "html.parser")
        def meta(name):
            tag = soup.find("meta", attrs={"property": name})
            return tag.get("content", "") if tag else ""
        play = self._stream(html)
        url = self.host + path
        item = {
            "vod_id": path, "vod_name": meta("og:title") or (soup.h1.get_text(" ", strip=True) if soup.h1 else path.strip("/")),
            "vod_pic": meta("og:image"), "vod_content": meta("og:description"),
            "vod_year": meta("og:video:release_date")[:4],
            "vod_actor": meta("og:video:actor"), "vod_director": meta("og:video:director"),
            "vod_play_from": "MissAV", "vod_play_url": "播放$" + (play or url),
        }
        return {"list": [item], "parse": 0, "jx": 0}

    def playerContent(self, flag, id, vipFlags):
        source = str(id or "")
        if not source:
            return {"parse": 0, "playUrl": "", "url": ""}
        if not re.search(r"\.m3u8(?:\?|$)|\.mp4(?:\?|$)", source, re.I):
            source = self._stream(self._get(self._path(source))) or source
        return {"parse": 0 if re.search(r"\.m3u8(?:\?|$)|\.mp4(?:\?|$)", source, re.I) else 1,
                "playUrl": "", "url": source,
                "header": {"User-Agent": self.HEADERS["User-Agent"], "Referer": self.host + "/"}}

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(?:m3u8|mp4)(?:\?|$)", str(url), re.I))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self.session.close()

    def _get(self, path, params=None):
        path = self._path(path)
        errors = []
        hosts = (self.host,) + tuple(host for host in self.HOSTS if host != self.host)
        for host in hosts:
            try:
                response = self.session.get(host + path, params=params, headers={"Referer": host + "/"}, timeout=15)
                response.encoding = "utf-8"
                if response.status_code == 200 and "Just a moment" not in response.text and "cf-browser-verification" not in response.text and "thumbnail" in response.text:
                    self.host = host
                    self.last_error = ""
                    return response.text
                errors.append(host + ": HTTP " + str(response.status_code) + (" Cloudflare" if "Just a moment" in response.text else ""))
            except requests.RequestException as exc:
                errors.append(host + ": " + type(exc).__name__)
        # Jina Reader can return the public HTML when Cloudflare challenges
        # the app's Python client. No account cookies or credentials are sent.
        try:
            reader = self.session.get(
                "https://r.jina.ai/https://missav.live" + path,
                params=params,
                headers={"X-Return-Format": "html"},
                timeout=25,
            )
            reader.encoding = "utf-8"
            if reader.status_code == 200 and "thumbnail" in reader.text:
                self.host = "https://missav.live"
                self.last_error = ""
                return reader.text
            errors.append("網頁讀取服務: HTTP " + str(reader.status_code))
        except requests.RequestException as exc:
            errors.append("網頁讀取服務: " + type(exc).__name__)
        self.last_error = "；".join(errors) or "未取得頁面"
        return ""

    def _diagnostic(self):
        return {"vod_id": "__missav_error__", "vod_name": "MissAV 暫無資料，點此查看原因",
                "vod_pic": "", "vod_remarks": self.last_error[:120] or "頁面解析失敗"}

    @staticmethod
    def _path(value):
        parsed = urlparse(str(value or ""))
        return "/" + (parsed.path or "/").lstrip("/")

    def _list(self, html):
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        items, seen = [], set()
        for card in soup.select("div.thumbnail.group"):
            link = next((a for a in card.find_all("a", href=True) if a.get("href") != "#"), None)
            title_link = card.select_one("a.text-secondary[href]")
            if not link or not title_link:
                continue
            path = self._path(link.get("href"))
            if path == "/" or path in seen:
                continue
            seen.add(path)
            image = card.select_one("img")
            duration = card.select_one("span.absolute.bottom-1.right-1")
            items.append({"vod_id": path,
                          "vod_name": title_link.get_text(" ", strip=True),
                          "vod_pic": urljoin(self.host, (image.get("data-src") or image.get("src") or "")) if image else "",
                          "vod_remarks": duration.get_text(" ", strip=True) if duration else ""})
        return items

    @staticmethod
    def _stream(html):
        if not html:
            return ""
        direct = re.search(r'https?:(?:\\/\\/|//)[^\s"\']+?\.m3u8', html, re.I)
        if direct:
            return direct.group(0).replace("\\/", "/")
        # The player packs its URL, while the same media UUID appears in seek images.
        match = re.search(r'c\.surrit\.com(?:\\/|/)([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})(?:\\/|/)seek', html, re.I)
        return "https://c.surrit.com/" + match.group(1) + "/playlist.m3u8" if match else ""

    @staticmethod
    def _page(value):
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return 1

    @staticmethod
    def _paged(items, page):
        return {"page": page, "pagecount": page + 1 if len(items) >= 12 else page,
                "limit": 12, "total": 99999 if items else 0, "list": items,
                "parse": 0, "jx": 0}
