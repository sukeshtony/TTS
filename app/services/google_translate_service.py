import os
import logging
from google.cloud import translate_v2 as translate
from google.auth.exceptions import DefaultCredentialsError

logger = logging.getLogger(__name__)

class GoogleTranslateService:
    _client = None
    _is_initialized = False

    @classmethod
    def _initialize_client(cls):
        if cls._is_initialized and cls._client:
            return
        try:
            cls._client = translate.Client()
            cls._is_initialized = True
            logger.info("Google Cloud Translate Client initialized successfully.")
        except DefaultCredentialsError as e:
            logger.error("Google Cloud credentials not found or invalid.")
            raise Exception("Google Cloud credentials not configured correctly.") from e
        except Exception as e:
            logger.error(f"Failed to initialize Translate Client: {e}")
            raise

    @classmethod
    async def translate_text(cls, text: str, target_lang: str) -> str:
        """
        Translates text using Google Cloud Translate V2.
        Currently using synchronous client in a thread-pool via asyncio if needed, 
        or directly if it's fast enough. The v2 client is synchronous.
        For true async, we use asyncio.to_thread.
        """
        if not text or not text.strip():
            return text

        if not cls._is_initialized:
            cls._initialize_client()

        import asyncio
        loop = asyncio.get_running_loop()
        
        def _sync_translate():
            try:
                result = cls._client.translate(text, target_language=target_lang)
                return result['translatedText']
            except Exception as e:
                logger.error(f"Translation failed: {e}")
                raise

        return await loop.run_in_executor(None, _sync_translate)
