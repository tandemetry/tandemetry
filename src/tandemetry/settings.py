from pydantic import BaseModel, PositiveInt, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ClickHouseSettings(BaseModel):
    host: str = "localhost"
    port: PositiveInt = 8123
    username: str = "default"
    password: SecretStr = SecretStr("")
    database: str = "tandemetry"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TANDEMETRY_", env_nested_delimiter="__")

    app_name: str = "tandemetry"
    clickhouse: ClickHouseSettings = ClickHouseSettings()
