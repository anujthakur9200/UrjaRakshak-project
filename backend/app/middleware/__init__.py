"""
UrjaRakshak — Middleware: Rate Limiting + Prometheus Metrics
=============================================================
Two middleware components:

1. RateLimitMiddleware
   - Simple in-memory token bucket per IP
   - 60 requests/min per IP (configurable)
   - Returns 429 with Retry-After header

2. MetricsMiddleware
   - Tracks request count, latency, error rates
   - Exposed at GET /metrics

Author: Vipin Baniya
"""

import time
import logging
from collections import defaultdict, deque
from typing import Dict, Deque, Callable
from datetime import datetime

from fastapi import Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


# ── Rate Limiter ──────────────────────────────────────────────────────────

class RateLimiter:
    """
    Sliding window rate limiter.
    Tracks request timestamps per IP in a deque.
    Thread-safe for single-process deployments (Render free tier is single process).
    """

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._windows: Dict[str, Deque[float]] = defaultdict(deque)

    def is_allowed(self, client_ip: str) -> tuple[bool, int]:
        """
        Check if request is allowed.
        Returns: (allowed: bool, requests_remaining: int)
        """
        now = time.time()
        window = self._windows[client_ip]

        # Remove timestamps outside the window
        while window and window[0] < now - self.window_seconds:
            window.popleft()

        if len(window) >= self.max_requests:
            retry_after = int(self.window_seconds - (now - window[0])) + 1
            return False, retry_after

        window.append(now)
        remaining = self.max_requests - len(window)
        return True, remaining


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware — 60 req/min per IP by default.
    Health checks and metrics endpoints are exempt.
    """

    EXEMPT_PATHS = {"/health", "/metrics", "/", "/api/openapi.json"}

    def __init__(self, app, max_requests: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self.limiter = RateLimiter(max_requests, window_seconds)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        allowed, value = self.limiter.is_allowed(client_ip)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "message": f"Too many requests. Retry after {value} seconds.",
                    "retry_after_seconds": value,
                },
                headers={"Retry-After": str(value)},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(value)
        return response


# ── Metrics Collector ─────────────────────────────────────────────────────

class MetricsCollector:
    """
    Lightweight Prometheus-compatible metrics collector.
    Exposes counters and histograms without external dependencies.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.start_time = time.time()
        self.request_count: Dict[str, int] = defaultdict(int)         # method:path → count
        self.error_count: Dict[str, int] = defaultdict(int)           # status_code → count
        self.latencies: Dict[str, list] = defaultdict(list)           # path → [ms...]
        self.total_requests = 0
        self.total_errors = 0

    def record_request(self, method: str, path: str, status_code: int, latency_ms: float):
        key = f"{method}:{path}"
        self.request_count[key] += 1
        self.latencies[path].append(latency_ms)
        # Keep only last 1000 latency samples per path
        if len(self.latencies[path]) > 1000:
            self.latencies[path] = self.latencies[path][-1000:]
        self.total_requests += 1
        if status_code >= 400:
            self.error_count[str(status_code)] += 1
            self.total_errors += 1

    def get_percentile(self, path: str, p: float) -> float:
        """Get latency percentile for a path"""
        lats = self.latencies.get(path, [])
        if not lats:
            return 0.0
        sorted_lats = sorted(lats)
        idx = int(len(sorted_lats) * p / 100)
        return sorted_lats[min(idx, len(sorted_lats) - 1)]

    def to_prometheus_text(self) -> str:
        """Emit Prometheus text format"""
        uptime = time.time() - self.start_time
        lines = [
            "# HELP urjarakshak_uptime_seconds Time since service start",
            "# TYPE urjarakshak_uptime_seconds gauge",
            f"urjarakshak_uptime_seconds {uptime:.1f}",
            "",
            "# HELP urjarakshak_requests_total Total HTTP requests",
            "# TYPE urjarakshak_requests_total counter",
            f"urjarakshak_requests_total {self.total_requests}",
            "",
            "# HELP urjarakshak_errors_total Total HTTP errors (4xx+5xx)",
            "# TYPE urjarakshak_errors_total counter",
            f"urjarakshak_errors_total {self.total_errors}",
            "",
        ]

        # Per-endpoint request counts
        lines.append("# HELP urjarakshak_endpoint_requests_total Requests per endpoint")
        lines.append("# TYPE urjarakshak_endpoint_requests_total counter")
        for key, count in sorted(self.request_count.items()):
            method, path = key.split(":", 1)
            safe_path = path.replace("/", "_").replace("-", "_").strip("_")
            lines.append(f'urjarakshak_endpoint_requests_total{{method="{method}",path="{path}"}} {count}')

        lines.append("")

        # Per-path latency p50, p95, p99
        lines.append("# HELP urjarakshak_request_latency_ms Request latency in milliseconds")
        lines.append("# TYPE urjarakshak_request_latency_ms summary")
        for path, lats in self.latencies.items():
            if lats:
                lines.append(f'urjarakshak_request_latency_ms{{path="{path}",quantile="0.50"}} {self.get_percentile(path, 50):.1f}')
                lines.append(f'urjarakshak_request_latency_ms{{path="{path}",quantile="0.95"}} {self.get_percentile(path, 95):.1f}')
                lines.append(f'urjarakshak_request_latency_ms{{path="{path}",quantile="0.99"}} {self.get_percentile(path, 99):.1f}')

        lines.append("")

        # Error counts by status code
        lines.append("# HELP urjarakshak_http_errors_by_code HTTP errors by status code")
        lines.append("# TYPE urjarakshak_http_errors_by_code counter")
        for code, count in self.error_count.items():
            lines.append(f'urjarakshak_http_errors_by_code{{status="{code}"}} {count}')

        return "\n".join(lines) + "\n"

    def to_json(self) -> dict:
        """JSON format for /health and dashboard use"""
        uptime = time.time() - self.start_time
        paths = list(self.latencies.keys())
        return {
            "uptime_seconds": round(uptime, 1),
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "error_rate_pct": round(self.total_errors / max(self.total_requests, 1) * 100, 2),
            "top_endpoints": dict(sorted(self.request_count.items(), key=lambda x: -x[1])[:10]),
            "latency_p50_ms": {p: round(self.get_percentile(p, 50), 1) for p in paths[:5]},
            "latency_p95_ms": {p: round(self.get_percentile(p, 95), 1) for p in paths[:5]},
            "recorded_at": datetime.utcnow().isoformat(),
        }


# Module-level singleton
metrics = MetricsCollector()


class MetricsMiddleware(BaseHTTPMiddleware):
    """Records latency and status for every request"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        latency_ms = (time.perf_counter() - start) * 1000
        metrics.record_request(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            latency_ms=latency_ms,
        )
        response.headers["X-Response-Time-Ms"] = f"{latency_ms:.1f}"
        return response
