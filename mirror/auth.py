"""Token auth: cookie (or Authorization header / ?token=) + per-IP lockout on failures."""
import hmac
import threading
import time
from collections import defaultdict, deque

COOKIE = "sm_token"
MAX_FAILS = 10
WINDOW = 300  # seconds


class Auth:
    def __init__(self, token: str):
        self._token = token.encode()
        self._fails = defaultdict(deque)
        self._lock = threading.Lock()

    def valid(self, candidate) -> bool:
        if not candidate:
            return False
        return hmac.compare_digest(candidate.encode(), self._token)

    @staticmethod
    def extract(request):
        """Return (token, came_from_query). Cookie wins, then header, then query."""
        cookie = request.cookies.get(COOKIE)
        if cookie:
            return cookie, False
        header = request.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            return header[7:].strip(), False
        return request.args.get("token", ""), True

    def locked_out(self, ip: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._fails[ip]
            while q and now - q[0] > WINDOW:
                q.popleft()
            return len(q) >= MAX_FAILS

    def record_failure(self, ip: str) -> None:
        with self._lock:
            self._fails[ip].append(time.monotonic())
