"""
Shared rate limiter.

A single Limiter instance used by every router decorator and registered on
app.state in main.py, so all per-route limits share one storage backend.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
