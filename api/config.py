from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    mongodb_uri: str = "mongodb://localhost:27017"
    database_name: str = "shiftwise"
    debug: bool = False


settings = Settings()
