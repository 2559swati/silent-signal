from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "SilentSignal AI"
    VERSION: str = "0.1.0"
    
    DATABASE_URL: str = "postgresql://postgres:password@postgres:5432/silentsignal"
    TEE_MODE: str = "demo"

    # Phase 12 Nitro Enclave settings (env-overridable; safe local defaults).
    NITRO_TRANSPORT: str = "loopback"  # loopback (local) | vsock (Nitro hardware)
    NITRO_CID: int = 16
    NITRO_PORT: int = 5000
    NITRO_TIMEOUT_S: float = 5.0
    NITRO_MAX_FRAME_BYTES: int = 262144
    # NITRO_DATA_KEY: Fernet key for the telemetry envelope (unset -> ephemeral local key).
    NITRO_DATA_KEY: str = ""
    # NITRO_PCR0: operator-supplied UNVERIFIED placeholder (never reported as attested).
    NITRO_PCR0: str = ""
    # Phase 13 KMS settings (parent-side only; never read inside the enclave).
    KMS_KEY_ID: str = ""
    KMS_REGION: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
