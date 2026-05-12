import os
import io
import re
import logging
import hashlib
import emoji
import redis.asyncio as redis
from pydub import AudioSegment
from google.cloud import texttospeech_v1 as text_to_speech
from google.auth.exceptions import DefaultCredentialsError
from google.genai import types
from google import genai
import asyncio

from app.core.config import settings

logger = logging.getLogger(__name__)

class TextToSpeechService:
    _client: text_to_speech.TextToSpeechAsyncClient = None
    _is_initialized = False
    _redis_client = None

    _VOICE_NAME = "en-US-Chirp3-HD-Puck"
    _DEFAULT_VOICE_NAME = _VOICE_NAME
    _LANGUAGE = "en-US"
    _SPEAKING_RATE = 1.0
    _VOLUME_DB = 2.0
    _LANGUAGE_VOICE_MAP = {
        "english":  "en-US-Chirp3-HD-Puck",
        "spanish":  "es-US-Chirp3-HD-Puck",
        "chinese":  "cmn-CN-Chirp3-HD-Puck",
        "hawaiian": "en-US-Chirp3-HD-Puck",
    }

    @classmethod
    async def get_redis(cls):
        if cls._redis_client is None:
            try:
                cls._redis_client = redis.Redis(
                    host=settings.redis_host,
                    port=settings.redis_port,
                    ssl=settings.redis_issl,
                    socket_timeout=settings.redis_timeout,
                    decode_responses=False
                )
                await cls._redis_client.ping()
                logger.info("Connected to Redis successfully.")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}")
                cls._redis_client = None
        return cls._redis_client

    @classmethod
    def _initialize_client(cls):
        if cls._is_initialized and cls._client:
            return
        try:
            cls._client = text_to_speech.TextToSpeechAsyncClient()
            cls._is_initialized = True
            logger.info("Google Cloud TextToSpeechAsyncClient initialized successfully.")
        except Exception as e:
            logger.error("Failed to initialize TextToSpeechAsyncClient.")
            raise e

    @staticmethod
    def _remove_emojis(text: str) -> str:
        try:
            return emoji.replace_emoji(text, replace='')
        except Exception:
            return re.sub(r'[\U00010000-\U0010ffff]', '', text)

    @classmethod
    async def check_text_safety(cls, text: str):
        if not text or not text.strip():
            raise Exception("Please provide text to evaluate.")

        project_id = os.getenv("GOOGLE_PROJECT_ID")
        location = os.getenv("GOOGLE_LOCATION")

        if not project_id or not location:
            logger.warning("Missing Vertex AI configuration: GOOGLE_PROJECT_ID or GOOGLE_LOCATION, skipping safety check.")
            return

        client = genai.Client(vertexai=True, project=project_id, location=location)

        config = types.GenerateContentConfig(
            temperature=0.0,
            safety_settings=[
                types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE),
                types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE),
                types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE),
                types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE),
            ]
        )

        prompt = f"""
        You are a strict safety evaluation system.
        Respond exactly with: "Inappropriate content detected." or "Content is safe."
        Text: "{text}"
        """

        loop = asyncio.get_running_loop()
        def _sync_generate():
            return client.models.generate_content(
                model='gemini-2.5-flash-lite',
                contents=prompt,
                config=config,
            )

        try:
            response = await loop.run_in_executor(None, _sync_generate)
            output_text = response.text.strip()
            if output_text != "Content is safe.":
                raise Exception("Inappropriate or unsafe content detected.")
        except Exception as e:
            logger.error(f"[Safety] Error: {e}")
            raise Exception("Failed to evaluate content safety.")

    @classmethod
    async def stream_speech(cls, text: str, voice_name: str = None):
        """
        Asynchronous generator for TTS streaming
        """
        if not text or not text.strip():
            return

        if not cls._is_initialized:
            cls._initialize_client()

        selected_voice = voice_name or cls._DEFAULT_VOICE_NAME
        cleaned_text = cls._remove_emojis(text)

        chunks = re.split(r'(?<=[.!?])\s+', cleaned_text)
        chunks = [c.strip() for c in chunks if c.strip()]

        language_code = "-".join(selected_voice.split("-")[:2])

        for i, chunk in enumerate(chunks):
            if not chunk: continue

            synthesis_input = text_to_speech.SynthesisInput(text=chunk)
            voice = text_to_speech.VoiceSelectionParams(
                language_code=language_code,
                name=selected_voice,
            )
            audio_config = text_to_speech.AudioConfig(
                audio_encoding=text_to_speech.AudioEncoding.OGG_OPUS,
                speaking_rate=cls._SPEAKING_RATE,
                volume_gain_db=cls._VOLUME_DB,
            )

            response = await cls._client.synthesize_speech(
                input=synthesis_input, voice=voice, audio_config=audio_config
            )

            logger.info(f"[TTS Stream] Yielding chunk {i+1}/{len(chunks)} ({len(chunk)} chars)")
            yield response.audio_content
