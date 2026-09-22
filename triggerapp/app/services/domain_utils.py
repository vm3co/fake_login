import os
from urllib.parse import urlparse
from fastapi import Request


def request_host(request: Request) -> str:
    """取出 request 的 public host（不含 port），優先 X-Forwarded-Host，再 Host。"""
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    return host.split(":")[0].strip().lower()


def accepted_default_hosts() -> set:
    """所有可視為「預設 trigger 網域」的 hostname 集合：
    TRIGGER_APP_URL 的 host + TRIGGER_APP_ETHAN_HOSTS（逗號分隔）。
    這些 host 對「未綁定 domain」的 page 一律放行，等同完整鏡像。"""
    hosts: set = set()
    raw = os.getenv("TRIGGER_APP_URL", "")
    if raw:
        try:
            h = (urlparse(raw).hostname or "").lower()
            if h:
                hosts.add(h)
        except Exception:
            pass
    for raw_domain in os.getenv("TRIGGER_APP_ETHAN_HOSTS", "").split(","):
        raw_domain = raw_domain.strip()
        if not raw_domain:
            continue
        # 容忍「https://selinks.sec-corp.cc」或裸「selinks.sec-corp.cc」兩種寫法
        parsed = urlparse(raw_domain if "//" in raw_domain else f"//{raw_domain}")
        h = (parsed.hostname or "").lower()
        if h:
            hosts.add(h)
    return hosts
