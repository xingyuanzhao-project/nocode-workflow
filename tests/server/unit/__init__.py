"""Service-level unit tests for :mod:`server.services` and supporting modules.

Every test here is fast (no Docker, no real network). Real Redis is
substituted with :mod:`fakeredis`; real HTTP is substituted with
:mod:`respx`.
"""
