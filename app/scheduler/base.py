"""APScheduler factory without registering domain jobs."""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler


def create_scheduler(timezone: str = "UTC") -> AsyncIOScheduler:
    """Create a paused scheduler; jobs are registered by future modules."""
    return AsyncIOScheduler(timezone=timezone)
