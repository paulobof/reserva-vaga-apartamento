from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    icond_login: str
    icond_senha: str
    evolution_api_key: str = ""
    whatsapp_number: str = "5511996293140"
    database_url: str = "sqlite+aiosqlite:///data/icond.db"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
