import json
import logging
from typing import Optional
from datetime import datetime, timezone
from fastapi import WebSocketException, status
from app.services.text_to_speech_service import TextToSpeechService

logger = logging.getLogger(__name__)

async def verify_ws_token(token: Optional[str]) -> dict:
    """
    Verifies the token by looking it up in Redis.
    Returns the decoded payload if valid.
    Raises WebSocketException if invalid.
    """
    if not token:
        logger.warning("No token provided for WebSocket connection")
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Missing token")

    redis_client = await TextToSpeechService.get_redis()
    if not redis_client:
        logger.error("Redis client not available")
        raise WebSocketException(code=status.WS_1011_INTERNAL_ERROR, reason="Internal Auth Error")

    try:
        # Get token data from Redis
        token_data = await redis_client.get(token)

        if not token_data:
            logger.warning(f"[Redis] Token not found: {token}")
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Token not found or expired")

        if isinstance(token_data, bytes):
            token_data = token_data.decode("utf-8")

        try:
            token_dict = json.loads(token_data)
        except json.JSONDecodeError:
            logger.error(f"[Redis] Failed to parse token JSON for {token}")
            raise WebSocketException(code=status.WS_1011_INTERNAL_ERROR, reason="Corrupted token data")

        session_id = token_dict.get("sessionId")
        if session_id:
            # Update last_accessed in session hash
            await redis_client.hset(
                f"session:{session_id}",
                "last_accessed",
                datetime.now(timezone.utc).isoformat()
            )
            logger.info(f"[Redis] Cached session timestamp for sessionId={session_id}")

        logger.info(f"[Redis] Token verified successfully")
        return token_dict

    except WebSocketException:
        raise
    except Exception as e:
        logger.error(f"[Redis] Error verifying token: {e}")
        raise WebSocketException(code=status.WS_1011_INTERNAL_ERROR, reason="Internal error verifying token")
