from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    backend_url: str = "http://localhost:8080"

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()
