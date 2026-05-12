import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    port: int = int(os.getenv("PORT", 8000))
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("REDIS_PORT", 6379))
    redis_issl: bool = os.getenv("REDIS_ISSL", "false").lower() == "true"
    redis_timeout: float = int(os.getenv("REDIS_TIMEOUT", 2000)) / 1000.0
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
