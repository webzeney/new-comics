import time
import urllib.robotparser
from urllib.parse import urlsplit

import requests

USER_AGENT = "NewComicsJPBot/0.1 (+https://new-comics.jp/about/)"
MIN_INTERVAL = 3.0
TIMEOUT = 30


class RobotsDisallowed(Exception):
    pass


class PoliteClient:
    def __init__(self, interval=MIN_INTERVAL):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "ja"})
        self.interval = interval
        self._last = {}
        self._robots = {}
        self.request_count = 0

    def _wait(self, host):
        last = self._last.get(host)
        if last is not None:
            wait = self.interval - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        self._last[host] = time.monotonic()

    def _robots_for(self, url):
        parts = urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        if base not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            self._wait(parts.netloc)
            res = self.session.get(base + "/robots.txt", timeout=TIMEOUT)
            self.request_count += 1
            if res.status_code == 200:
                rp.parse(res.text.splitlines())
            elif res.status_code in (401, 403):
                rp.disallow_all = True
            else:
                rp.allow_all = True
            self._robots[base] = rp
        return self._robots[base]

    def get(self, url):
        if not self._robots_for(url).can_fetch(USER_AGENT, url):
            raise RobotsDisallowed(url)
        self._wait(urlsplit(url).netloc)
        res = self.session.get(url, timeout=TIMEOUT)
        self.request_count += 1
        res.raise_for_status()
        if not res.encoding or res.encoding.lower() == "iso-8859-1":
            res.encoding = res.apparent_encoding
        return res.text
