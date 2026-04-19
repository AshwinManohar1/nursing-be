"""Rate limiting for auth endpoints to prevent brute force attacks."""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# Login: 10 attempts per 15 minutes per IP
LOGIN_RATE_LIMIT = "10/15minute"
