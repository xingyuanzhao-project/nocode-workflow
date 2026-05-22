"""Application-owned Redis connection pool.

Celery owns its own broker and result-backend connections (driven by
:mod:`server.celery_app`). This module owns the *application* connection
used by :class:`server.services.run_registry.RunRegistry` and the
``/api/health`` endpoint. Keeping the two concerns in separate modules
avoids accidental reuse of Celery's connection pool for application
traffic.

Contents and relationships
--------------------------

- :func:`build_redis_client` — returns a :class:`redis.Redis` instance
  backed by a module-level :class:`redis.ConnectionPool`, keyed by
  ``(url, db)``. ``decode_responses=True`` so reads return :class:`str`
  rather than :class:`bytes`.

How the rest of the system uses this module
-------------------------------------------

- :mod:`server.services.run_registry` calls :func:`build_redis_client`
  with ``db=settings.redis_app_db`` once at construction.
- :mod:`server.routes.health` calls the same function and pings the
  returned client.

Invariants enforced by this module
----------------------------------

- One connection pool per ``(redis_url, db)`` tuple per process.
- ``decode_responses=True`` is always set; call sites never have to
  ``.decode()`` bytes explicitly.
"""

from __future__ import annotations

from typing import Dict, Tuple

import redis


_CONNECTION_POOLS: Dict[Tuple[str, int], redis.ConnectionPool] = {}
"""Module-level cache of :class:`redis.ConnectionPool` keyed by
``(base_redis_url, db_index)``. Populated lazily by
:func:`build_redis_client`."""


def build_redis_client(base_redis_url: str, db_index: int) -> redis.Redis:
    """Return a :class:`redis.Redis` bound to the requested logical DB.

    Creates and caches one :class:`redis.ConnectionPool` per
    ``(base_redis_url, db_index)`` tuple so repeated calls share
    connections. Every returned client has ``decode_responses=True``.

    Args:
        base_redis_url (str): Base URL without a database suffix, for
            example ``"redis://localhost:6379"``.
        db_index (int): Redis logical database index.

    Returns:
        redis.Redis: A client backed by the cached pool.
    """
    pool_key: Tuple[str, int] = (base_redis_url.rstrip("/"), db_index)
    existing_pool = _CONNECTION_POOLS.get(pool_key)
    if existing_pool is None:
        full_url = f"{pool_key[0]}/{db_index}"
        existing_pool = redis.ConnectionPool.from_url(
            full_url, decode_responses=True
        )
        _CONNECTION_POOLS[pool_key] = existing_pool
    return redis.Redis(connection_pool=existing_pool)
