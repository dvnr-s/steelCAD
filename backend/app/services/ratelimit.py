"""
Shared rate limiter.

A single Limiter instance used by every router decorator and registered on
app.state in main.py, so all per-route limits share one storage backend.

Client identity for limiting
----------------------------
In production the backend port is NOT published — nginx is the only thing that
connects to it (docker-compose.prod.yml), and uvicorn is not told to trust that
proxy hop. So Starlette's `request.client.host` (what slowapi's stock
`get_remote_address` returns) is nginx's internal IP for EVERY request, from
every user. Keyed on that, all callers share one bucket: a single actor sending
5 login attempts/minute would exhaust the `5/minute` login limit for the whole
company (an unauthenticated, low-effort denial of service), and the same holds
for the PDF (`10/minute`) and price (`120/minute`) limits.

nginx authoritatively sets `X-Real-IP` to the connecting client's address
(`proxy_set_header X-Real-IP $remote_addr`), replacing any value the client
tried to send. Because the backend is reachable ONLY through nginx in
production, that header is a trustworthy, un-forgeable per-client key — so we
key on it when present and fall back to the socket address in dev (no proxy, so
the header is absent). We deliberately do NOT parse the leftmost
`X-Forwarded-For`, which a client could spoof to rotate identities and evade
every limit.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def client_ip(request: Request) -> str:
    """Rate-limit key: the real client IP.

    Prefer `X-Real-IP` (set by our own nginx to the connecting peer, overwriting
    any inbound value) so limits are per-client behind the reverse proxy. Fall
    back to the direct socket address in dev, where there is no proxy and the
    header is absent.
    """
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        # A single header value; guard against a stray comma-joined list.
        return real_ip.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=client_ip)
