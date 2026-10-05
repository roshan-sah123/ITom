"""Small process-local cache for computed dashboard summaries."""

from __future__ import annotations

import asyncio
import copy
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable, Optional

logger = logging.getLogger("itom.summary_cache")
SUMMARY_CACHE_TTL_SECONDS = 300


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float


class AsyncSummaryCache:
    """Cache JSON-safe summary payloads without sharing mutable response data."""

    def __init__(self, ttl_seconds: float = 30.0) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than zero")
        self.ttl_seconds = float(ttl_seconds)
        self._entries: dict[str, _CacheEntry] = {}
        self._generations: dict[str, int] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def get_or_load(
        self,
        key: str,
        loader: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Return a fresh value, loading once per key when the entry is stale.

        If refreshing an expired entry fails, retain the last good payload. Its
        original ``generated_at`` and freshness fields remain intact so clients
        can still see that the data itself is old.
        """
        entry = self._entries.get(key)
        if entry is not None and entry.expires_at > time.monotonic():
            return copy.deepcopy(entry.value)

        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            while True:
                now = time.monotonic()
                entry = self._entries.get(key)
                if entry is not None and entry.expires_at > now:
                    return copy.deepcopy(entry.value)

                generation = self._generations.get(key, 0)
                last_good = entry
                try:
                    value = await loader()
                except Exception:
                    if (
                        last_good is not None
                        and self._generations.get(key, 0) == generation
                    ):
                        logger.warning(
                            "Summary refresh failed for %s; serving its last good payload",
                            key,
                            exc_info=True,
                        )
                        return copy.deepcopy(last_good.value)
                    raise

                # A successful sync may have committed while the loader was
                # querying. Discard that pre-sync result and read the new state.
                if self._generations.get(key, 0) != generation:
                    continue

                self._entries[key] = _CacheEntry(
                    value=copy.deepcopy(value),
                    expires_at=time.monotonic() + self.ttl_seconds,
                )
                return copy.deepcopy(value)

    def invalidate(self, *keys: str) -> None:
        """Expire named summaries, or all summaries when no keys are supplied."""
        selected = set(keys) if keys else (
            set(self._entries) | set(self._generations) | set(self._locks)
        )
        for key in selected:
            self._entries.pop(key, None)
            self._generations[key] = self._generations.get(key, 0) + 1


# Keep summaries warm for typical dashboard navigation. The 10-minute sync
# cadence invalidates successful source updates immediately after their commit.
summary_cache = AsyncSummaryCache(ttl_seconds=SUMMARY_CACHE_TTL_SECONDS)


def summary_cache_key(session: Any, summary_name: str) -> str:
    """Scope summaries to their database engine to prevent cross-DB reuse."""
    bind = getattr(session, "bind", None) if session is not None else None
    return f"engine:{id(bind)}:{summary_name}" if bind is not None else summary_name


def invalidate_summaries_for_sources(
    successful_sources: Iterable[str],
    *,
    cache: Optional[AsyncSummaryCache] = None,
    session: Any = None,
) -> tuple[str, ...]:
    """Invalidate only summaries affected by sources whose DB commit succeeded."""
    normalized = {str(source).strip().upper() for source in successful_sources}
    if "ALL" in normalized:
        normalized.update({"SOLARWINDS", "INTUNE"})

    keys = {"cmdb"} if normalized & {"SOLARWINDS", "INTUNE"} else set()
    if "SOLARWINDS" in normalized:
        keys.add("solarwinds")
    if "INTUNE" in normalized:
        keys.add("intune")

    if keys:
        scoped_keys = tuple(sorted(summary_cache_key(session, key) for key in keys))
        (cache or summary_cache).invalidate(*scoped_keys)
        return scoped_keys
    return ()
