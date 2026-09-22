from __future__ import annotations

from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser


class RobotsCache:
    def __init__(self, user_agent: str) -> None:
        self._user_agent = user_agent
        self._cache: dict[str, RobotFileParser] = {}

    def is_allowed_without_fetch(self, url: str) -> bool:
        parsed = urlsplit(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        parser = self._cache.get(robots_url)
        if parser is None:
            return True
        return parser.can_fetch(self._user_agent, url)
