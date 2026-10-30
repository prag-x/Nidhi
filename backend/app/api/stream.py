"""Server-Sent Events for live dashboard updates.

EventSource cannot send an Authorization header, so the client first exchanges its bearer token
for a short-lived stream token and passes that in the query string.
"""

import asyncio

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..db import SessionLocal
from ..deps import get_current_user
from ..models import User
from ..security import create_access_token, decode_token
from ..services.events import Subscriber, broker
from ..services.permissions import is_global

router = APIRouter(tags=["stream"])
STREAM_TOKEN_MINUTES = 2
HEARTBEAT_SECONDS = 20


@router.post("/stream/token")
def stream_token(user: User = Depends(get_current_user)):
    return {"token": create_access_token(user.id, f"stream:{user.role}", minutes=STREAM_TOKEN_MINUTES)}


@router.get("/stream")
async def stream(request: Request, token: str):
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired stream token") from None
    if not str(payload.get("role", "")).startswith("stream:"):
        raise HTTPException(401, "Not a stream token")
    db = SessionLocal()
    try:
        user = db.get(User, int(payload["sub"]))
        if user is None or not user.is_active:
            raise HTTPException(401, "Account not found or disabled")
        sub = Subscriber(user_id=user.id, unit_id=user.org_unit_id, is_global=is_global(user),
                         institution_id=user.institution_id if user.role == "INSTITUTION" else None)
    finally:
        db.close()
    broker.subscribe(sub)

    async def events():
        try:
            yield "retry: 5000\n\nevent: ready\ndata: {}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(sub.queue.get(), timeout=HEARTBEAT_SECONDS)
                    yield f"data: {message}\n\n"
                except TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            broker.unsubscribe(sub)

    return StreamingResponse(
        events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
