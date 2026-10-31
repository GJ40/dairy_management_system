from __future__ import annotations

from typing import Any, Awaitable, Callable

from fastapi import BackgroundTasks

MailTask = Callable[..., Awaitable[Any]]


async def deliver_or_queue(
    background: BackgroundTasks | None,
    task: MailTask,
    **kwargs: Any,
) -> None:
    """Send now when there is no request context, else after the response.

    Awaiting SMTP inside the request makes forgot-password measurably slower
    for addresses that exist, which leaks account existence even though the
    response body is identical. FastAPI runs background tasks after the
    response is sent, so HTTP latency stops depending on the mail server.
    """
    if background is None:
        await task(**kwargs)
        return
    background.add_task(task, **kwargs)
