"""Durable completion fixtures shared by local session tests."""
import asyncio
import time

from tools import async_delegation as delegation


def pending(key, name):
    evt = {"type": "async_delegation", "session_key": key, "delegation_id": name,
           "summary": name, "status": "completed", "dispatched_at": time.time()}
    delegation._persist_dispatch(evt)
    delegation._persist_completion(evt, {"status": "completed", "summary": name})
    return evt


async def drain(adapter):
    while adapter._background_tasks:
        await asyncio.gather(*list(adapter._background_tasks))
        # gather() over tasks that are ALL already done completes without yielding (3.12+), so a
        # finished task whose queued _background_tasks.discard callback has not run yet would spin
        # this loop forever; yield once so those done-callbacks run before re-checking.
        await asyncio.sleep(0)
