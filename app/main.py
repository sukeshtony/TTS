from dotenv import load_dotenv
load_dotenv()

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.websocket_route import router as websocket_router
from app.services.text_to_speech_service import TextToSpeechService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="TTS Microservice")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(websocket_router)

@app.on_event("startup")
async def startup_event():
    logger.info("Initializing services...")
    # Trigger Redis connection check
    await TextToSpeechService.get_redis()

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "tts_microservice"}

if __name__ == "__main__":
    import uvicorn
    from app.core.config import settings
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port, reload=True)
