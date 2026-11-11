"""Periodic cleanup for expired private uploads."""

from __future__ import annotations

import asyncio
import logging

from app.core.config import Settings
from app.services.storage import delete_expired_uploads

logger = logging.getLogger(__name__)


async def retention_cleanup_loop(settings: Settings) -> None:
    while True:
        try:
            removed = await asyncio.to_thread(delete_expired_uploads, settings)
            if removed:
                logger.info("Removed %d expired temporary upload(s)", removed)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Never include filenames, image data, or request metadata in cleanup logs.
            logger.exception("Temporary upload cleanup failed")
        await asyncio.sleep(settings.cleanup_interval_seconds)
