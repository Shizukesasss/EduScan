"""Limit expensive API routes before FastAPI parses the request body."""

from collections import OrderedDict
from collections.abc import Callable
from math import ceil
from threading import Lock
from time import monotonic

from fastapi import HTTPException, Request
from fastapi.routing import APIRoute


class RequestRateLimiter:
    def __init__(self, policies: dict[str, tuple[int, int]], *,
                 clock: Callable[[], float] = monotonic, max_clients: int = 4096) -> None:
        self.policies = policies
        self.clock = clock
        self.max_clients = max_clients
        self.buckets: dict[str, OrderedDict[str, tuple[float, float]]] = {
            category: OrderedDict() for category in policies
        }
        self.lock = Lock()

    def retry_after(self, category: str, client: str) -> int | None:
        per_minute, burst = self.policies[category]
        interval = 60 / per_minute
        tolerance = (burst - 1) * interval
        with self.lock:
            now = self.clock()
            bucket = self.buckets[category]
            previous = bucket.get(client)
            if previous is None and len(bucket) >= self.max_clients:
                oldest, (_, last_accepted) = next(iter(bucket.items()))
                # One minute without an accepted request fully restores any bucket.
                until_idle = last_accepted + 60 - now
                if until_idle > 0:
                    return ceil(until_idle)
                del bucket[oldest]

            # Reserve one interval of work while allowing the configured burst.
            scheduled = max(now, previous[0]) if previous else now
            wait = scheduled - now - tolerance
            if wait > 1e-9:
                return ceil(wait)

            bucket[client] = (scheduled + interval, now)
            bucket.move_to_end(client)
            return None


def rate_limit(category: str):
    def decorate(endpoint):
        endpoint.rate_limit_category = category
        return endpoint
    return decorate


class RateLimitedRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        category = getattr(self.endpoint, "rate_limit_category", None)
        if category is None:
            return handler

        async def handle(request: Request):
            client = request.client.host if request.client else "unknown"
            retry_after = request.app.state.request_limiter.retry_after(category, client)
            if retry_after is not None:
                raise HTTPException(429, f"Too many {category} requests. Try again shortly.",
                                    headers={"Retry-After": str(retry_after)})
            return await handler(request)

        return handle
