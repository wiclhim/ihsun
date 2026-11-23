# -*- coding: utf-8 -*-
"""Single-video Huangguo channel for the TVBox Python Spider interface."""

import json
import re

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    HOST = "https://huangguoai.com"
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

    def __init__(self):
        self.video_ids = []
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
        return "黃果短劇（單片）"

    def homeContent(self, filter):
        return {"class": [{"type_id": "favorites", "type_name": "我的收藏"}],
                "list": self.homeVideoContent().get("list", [])}

    def homeVideoContent(self):
        return {"list": [self._summary(video_id) for video_id in self.video_ids]}

    def categoryContent(self, tid, pg, filter, extend):
        page = max(1, int(pg))
        items = self.homeVideoContent()["list"] if tid == "favorites" and page == 1 else []
        return {"page": page, "pagecount": 1, "limit": max(1, len(self.video_ids)),
                "total": len(self.video_ids), "list": items}

    def detailContent(self, ids):
        video_id = self._video_id(ids[0])
        data = self._api("GET", "/api/videos/" + video_id)
        episodes = data.get("episodes") or []
        if not episodes:
            episodes = [{"ep_num": number} for number in range(1, int(data.get("episode_count") or 1) + 1)]
        play = []
        for episode in episodes:
            number = int(episode.get("ep_num"))
            label = str(episode.get("title") or "第%d集" % number).replace("#", " ").replace("$", " ")
            play.append("%s$%s:%d" % (label, video_id, number))
        return {"list": [{
            "vod_id": video_id,
            "vod_name": data.get("title") or video_id,
            "vod_pic": data.get("cover") or "",
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

    def searchContent(self, key, quick, pg="1"):
        return {"list": []}

    def _summary(self, video_id):
        data = self._api("GET", "/api/videos/" + self._video_id(video_id))
        return {"vod_id": video_id, "vod_name": data.get("title") or video_id,
                "vod_pic": data.get("cover") or "",
                "vod_remarks": "更新至%s集" % (data.get("episode_count") or 1)}

    def _api(self, method, path):
        response = self.session.request(method, self.HOST + path,
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
