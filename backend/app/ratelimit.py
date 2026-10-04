import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


def limit(max_calls: int, per_seconds: int):
    """Simple in-memory limiter per client IP. Fine for one server process."""
    hits = defaultdict(deque)

    def dependency(request: Request):
        key = request.client.host if request.client else "unknown"
        now = time.time()
        q = hits[key]
        while q and now - q[0] > per_seconds:
            q.popleft()
        if len(q) >= max_calls:
            raise HTTPException(status_code=429, detail="Too many requests. Please wait a moment and try again.")
        q.append(now)

    return dependency


login_limit = limit(10, 60)      # 10 login attempts per minute
signup_limit = limit(5, 3600)    # 5 signups per hour
chat_limit = limit(30, 60)       # 30 chat messages per minute