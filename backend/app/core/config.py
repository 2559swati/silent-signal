from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "SilentSignal AI"
    VERSION: str = "0.1.0"
    
    DATABASE_URL: str = "postgresql://postgres:password@postgres:5432/silentsignal"
    TEE_MODE: str = "demo"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
