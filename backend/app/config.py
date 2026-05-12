from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+psycopg://cocktailuser:changeme@localhost:5432/cocktails"
    )
    pool_size: int = 5
    max_overflow: int = 5
    log_level: str = "INFO"


settings = Settings()
