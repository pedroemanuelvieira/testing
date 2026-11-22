"""Assistente (chatbot)."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from ..deps import assistant, bad_request, not_found

router = APIRouter(prefix="/api/chat", tags=["assistente"])


class ChatBody(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    project_id: Optional[str] = None
    page: Optional[str] = None


@router.get("/status")
def status() -> dict[str, Any]:
    return assistant().status()


@router.post("")
def chat(body: ChatBody) -> dict[str, Any]:
    try:
        return assistant().chat(body.message, body.conversation_id, body.project_id, body.page)
    except ValueError as exc:
        raise bad_request(exc) from exc


@router.get("/{conversation_id}")
def history(conversation_id: str) -> dict[str, Any]:
    try:
        return assistant().history(conversation_id)
    except KeyError as exc:
        raise not_found("Conversa") from exc


@router.delete("/{conversation_id}")
def delete(conversation_id: str) -> dict[str, str]:
    try:
        assistant().store.delete(conversation_id)
    except KeyError as exc:
        raise not_found("Conversa") from exc
    return {"status": "apagada"}
