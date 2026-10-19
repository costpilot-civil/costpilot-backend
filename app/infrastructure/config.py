from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    postgres_db: str
    postgres_user: str
    postgres_password: str
    postgres_host: str = "localhost"
    postgres_port: int = 5434
    tender_max_upload_bytes: int = Field(default=20 * 1024 * 1024, gt=0)
    models_config_path: str = "config/config.yml"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
