from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from polaris_x.api.authz import current_user
from polaris_x.api.errors import error_response
from polaris_x.chatbot.llm import provider_from_config
from polaris_x.chatbot.service import respond
from polaris_x.db.models import ChatMessage, ChatSession
from polaris_x.extensions import db_session

bp = Blueprint("chat", __name__, url_prefix="/api/v1/chat/conversations")

class CreateConversation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metadata: dict = Field(default_factory=dict)

class SendMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=8000)

def _conversation(session, user, conversation_id):
    item = session.get(ChatSession, conversation_id)
    if item is None or item.user_id != user.id:
        return None
    return item

def _message(item):
    return {"id": str(item.id), "role": item.role, "content": item.content, "created_at": item.created_at.isoformat(), "tool_summaries": item.source_references.get("tool_summaries", []) if item.role == "assistant" else []}

@bp.post("")
@jwt_required()
def create_conversation():
    data = CreateConversation.model_validate(request.get_json(silent=False) or {})
    session, user = db_session(), current_user()
    item = ChatSession(user_id=user.id, metadata_json=data.metadata)
    session.add(item); session.commit()
    return jsonify(conversation={"id": str(item.id), "started_at": item.started_at.isoformat(), "archived_at": None}), 201

@bp.get("")
@jwt_required()
def list_conversations():
    session, user = db_session(), current_user()
    try: page, per_page = int(request.args.get("page", 1)), int(request.args.get("per_page", 20))
    except ValueError: return error_response("invalid_parameter", "page and per_page must be integers.", 400)
    if not 1 <= page <= 1_000_000 or not 1 <= per_page <= 100: return error_response("invalid_parameter", "page must be >= 1 and per_page must be between 1 and 100.", 400)
    query = select(ChatSession).where(ChatSession.user_id == user.id).order_by(ChatSession.started_at.desc())
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    items = session.execute(query.offset((page - 1) * per_page).limit(per_page)).scalars().all()
    return jsonify(conversations=[{"id": str(item.id), "started_at": item.started_at.isoformat(), "archived_at": item.ended_at.isoformat() if item.ended_at else None} for item in items], total=total, page=page, per_page=per_page)

@bp.get("/<uuid:conversation_id>")
@jwt_required()
def get_conversation(conversation_id):
    session, user = db_session(), current_user(); item = _conversation(session, user, conversation_id)
    if item is None: return error_response("not_found", "Conversation not found.", 404)
    messages = session.execute(select(ChatMessage).where(ChatMessage.session_id == item.id).order_by(ChatMessage.created_at, ChatMessage.id)).scalars().all()
    return jsonify(conversation={"id": str(item.id), "started_at": item.started_at.isoformat(), "archived_at": item.ended_at.isoformat() if item.ended_at else None, "messages": [_message(message) for message in messages]})

@bp.post("/<uuid:conversation_id>/messages")
@jwt_required()
def send_message(conversation_id):
    data = SendMessage.model_validate(request.get_json(silent=False) or {})
    session, user = db_session(), current_user(); conversation = _conversation(session, user, conversation_id)
    if conversation is None: return error_response("not_found", "Conversation not found.", 404)
    if conversation.ended_at is not None: return error_response("conflict", "Conversation is archived.", 409)
    user_message = ChatMessage(session_id=conversation.id, role="user", content=data.content, created_at=datetime.now(timezone.utc), source_references={})
    session.add(user_message); session.flush()
    assistant, summaries = respond(session, user, conversation, user_message, provider_from_config(current_app.config))
    session.commit()
    return jsonify(conversation_id=str(conversation.id), user_message_id=str(user_message.id), assistant_message_id=str(assistant.id), response_text=assistant.content, tool_summaries=summaries)

@bp.delete("/<uuid:conversation_id>")
@jwt_required()
def archive_conversation(conversation_id):
    session, user = db_session(), current_user(); item = _conversation(session, user, conversation_id)
    if item is None: return error_response("not_found", "Conversation not found.", 404)
    if item.ended_at is None:
        item.ended_at = datetime.now(timezone.utc); session.commit()
    return "", 204
