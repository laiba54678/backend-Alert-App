# app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Safe defaults so it works even if Render env vars are empty/missing
    MONGO_URI: str = "mongodb+srv://laiba:laiba123456@cluster0.gaxu9d6.mongodb.net/?retryWrites=true&w=majority&authSource=admin"
    MONGO_DB: str = "laiba"

    KAFKA_BOOTSTRAP_SERVERS: str = ""   # leave empty until you configure Kafka
    KAFKA_TOPIC_ALERTS: str = "alerts"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
