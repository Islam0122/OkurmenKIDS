"""Per-client-IP rate limits for the public (no login) training API.
Rates live in REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]. The IP is only part
of the cache key for the window — never stored."""
from rest_framework.throttling import SimpleRateThrottle


class _IPThrottle(SimpleRateThrottle):
    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class TrainingReadThrottle(_IPThrottle):
    scope = "training_read"


class TrainingStartThrottle(_IPThrottle):
    scope = "training_start"


class TrainingWriteThrottle(_IPThrottle):
    scope = "training_write"
