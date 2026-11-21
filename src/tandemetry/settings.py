from pydantic import BaseModel, PositiveFloat, PositiveInt, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ClickHouseSettings(BaseModel):
    host: str = "localhost"
    port: PositiveInt = 8123
    username: str = "default"
    password: SecretStr = SecretStr("")
    database: str = "tandemetry"


class KafkaSettings(BaseModel):
    bootstrap_servers: str = "localhost:29092"
    events_topic: str = "events.normalized"
    consumer_group: str = "tandemetry-clickhouse"
    raw_topic: str = "raw.github"
    normalizer_group: str = "tandemetry-normalizer"
    normalizer_max_poll_interval_ms: PositiveInt = 7_200_000
    max_message_bytes: PositiveInt = 33_554_432
    max_batch_records: PositiveInt = 500
    poll_timeout_ms: PositiveInt = 1000


class GitHubSettings(BaseModel):
    webhook_secret: SecretStr = SecretStr("")
    client_id: str = ""
    private_key: SecretStr = SecretStr("")
    api_url: str = "https://api.github.com"
    request_timeout_s: PositiveFloat = 10.0
    retry_initial_s: PositiveFloat = 1.0
    retry_max_s: PositiveFloat = 60.0
    rate_limit_max_wait_s: PositiveFloat = 3600.0
    batch_deadline_s: PositiveFloat = 6000.0


class ApiSettings(BaseModel):
    host: str = "127.0.0.1"
    port: PositiveInt = 8000
    max_body_bytes: PositiveInt = 26_214_400


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TANDEMETRY_", env_nested_delimiter="__")

    app_name: str = "tandemetry"
    clickhouse: ClickHouseSettings = ClickHouseSettings()
    kafka: KafkaSettings = KafkaSettings()
    github: GitHubSettings = GitHubSettings()
    api: ApiSettings = ApiSettings()
