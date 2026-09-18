"""Caller identity for the FD backend.

Browser apps (Toolstation, upload-canvas, ...) call this backend directly, so
this package is the security boundary. See auth/deps.py for the dependency and
AUTH_MODE for the rollout switch.
"""
