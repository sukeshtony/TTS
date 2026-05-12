import json
import base64
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.services.text_to_speech_service import TextToSpeechService
from app.services.google_translate_service import GoogleTranslateService
from app.core.security import verify_ws_token

logger = logging.getLogger(__name__)

router = APIRouter()

_LANG_CONFIG = {
    "english":  (None,    "en-US-Chirp3-HD-Puck"),
    "spanish":  ("es",    "es-US-Chirp3-HD-Puck"),
    "hawaiian": ("haw",   "en-US-Chirp3-HD-Puck"),
}
_DEFAULT_VOICE = "en-US-Chirp3-HD-Puck"

def _resolve(voice: str):
    return _LANG_CONFIG.get(voice, (None, _DEFAULT_VOICE))

@router.websocket("/tts_stream")
async def tts_stream(websocket: WebSocket, token: str = Query(None)):
    """
    WebSocket endpoint for TTS streaming.
    """
    try:
        # Validate token first
        payload = await verify_ws_token(token)
        await websocket.accept()
        logger.info(f"[TTS WS] Connection opened for user: {payload.get('user_id', 'unknown')}")
    except Exception as e:
        logger.warning(f"[TTS WS] Connection rejected: {e}")
        return

    try:
        while True:
            message = await websocket.receive_text()
            if not message:
                break
                
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                await websocket.send_json({"error": "Invalid JSON"})
                continue

            text = data.get("text")
            voice = data.get("voice", "english").lower()
            msg_type = data.get("type", "").strip()
            request_id = data.get("id")

            async def send_msg(payload):
                if request_id:
                    payload["id"] = request_id
                try:
                    await websocket.send_json(payload)
                except Exception as e:
                    logger.error(f"Failed to send WS message: {e}")

            translate_code, voice_name = _resolve(voice)

            if msg_type == "Instruction" and text:
                try:
                    if text.startswith("example_instruction:"):
                        parts = text.split(";example_content:")
                        if len(parts) == 2:
                            instruction_part = parts[0].replace("example_instruction:", "").strip()
                            content_part = parts[1].strip()

                            idx = 0
                            # 1. Instruction in selected language
                            if translate_code:
                                instruction_part = await GoogleTranslateService.translate_text(instruction_part, translate_code)
                            
                            logger.info(f"[TTS WS] Streaming split example_instruction ({voice_name}) and example_content (en)")
                            async for audio_chunk in TextToSpeechService.stream_speech(instruction_part, voice_name):
                                b64_audio = base64.b64encode(audio_chunk).decode('utf-8')
                                await send_msg({"audio": b64_audio, "index": idx, "done": False})
                                idx += 1

                            # 2. Content ALWAYS in English regardless of user's voice setting
                            async for audio_chunk in TextToSpeechService.stream_speech(content_part, _DEFAULT_VOICE):
                                b64_audio = base64.b64encode(audio_chunk).decode('utf-8')
                                await send_msg({"audio": b64_audio, "index": idx, "done": False})
                                idx += 1

                            await send_msg({"done": True})
                            logger.info("[TTS WS] Streaming completed for example_instruction")
                            continue
                    else:
                        if translate_code:
                            text = await GoogleTranslateService.translate_text(text.strip(), translate_code)

                except Exception as e:
                    logger.error(f"[TTS WS] Instruction formatting/translation error: {e}")

            if not text:
                await send_msg({"error": "No text provided"})
                continue

            logger.info(f"[TTS WS] Streaming request for: {text[:20]}...")
            
            try:
                # Optionally check safety
                # await TextToSpeechService.check_text_safety(text)
                
                idx = 0
                async for audio_chunk in TextToSpeechService.stream_speech(text, voice_name):
                    b64_audio = base64.b64encode(audio_chunk).decode('utf-8')
                    await send_msg({"audio": b64_audio, "index": idx, "done": False})
                    idx += 1

                await send_msg({"done": True})
                logger.info("[TTS WS] Streaming completed")

            except Exception as e:
                logger.error(f"[TTS WS] Streaming error: {e}")
                await send_msg({"error": "Streaming failed"})
                
    except WebSocketDisconnect:
        logger.info("[TTS WS] Client disconnected")
    except Exception as e:
        logger.error(f"[TTS WS] Socket error: {e}")
    finally:
        logger.info("[TTS WS] Connection closed")
