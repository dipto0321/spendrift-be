from slowapi import Limiter
from slowapi.util import get_remote_address

# Default limit applied (via SlowAPIMiddleware) to every route that has no
# explicit @limiter.limit(...) decorator of its own. Routes with a decorator
# (auth register/login/refresh) use only their own tighter limit instead of
# stacking with this one. Routes marked @limiter.exempt (auth sign-out) skip
# rate limiting entirely.
DEFAULT_RATE_LIMIT = "60/minute"

# Create a limiter instance that limits by client IP address
limiter = Limiter(key_func=get_remote_address, default_limits=[DEFAULT_RATE_LIMIT])
