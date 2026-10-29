from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

BASE_DIR = Path(__file__).resolve().parents[2]

DEFAULT_JWT_SECRET = "dairy_dev_super_secret_jwt_key_at_least_32_chars_long"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    node_env: str = Field(default="development", validation_alias="NODE_ENV")
    port: int = Field(default=8000, validation_alias="PORT")
    tz: str = Field(default="Asia/Kolkata", validation_alias="TZ")

    database_url: SecretStr | None = Field(default=None, validation_alias="DATABASE_URL")
    db_dialect: str = Field(default="mysql", validation_alias="DB_DIALECT")
    db_host: str = Field(default="localhost", validation_alias="DB_HOST")
    db_port: int = Field(default=3307, validation_alias="DB_PORT")
    db_name: str = Field(default="dairy_db", validation_alias="DB_NAME")
    db_user: str = Field(default="root", validation_alias="DB_USER")
    db_password: SecretStr = Field(default=SecretStr("root"), validation_alias="DB_PASSWORD")
    db_logging: bool = Field(default=False, validation_alias="DB_LOGGING")

    cors_origins: str = Field(
        default="http://localhost:5173,http://localhost:3000",
        validation_alias="CORS_ORIGINS",
    )

    jwt_secret: SecretStr = Field(
        default=SecretStr(DEFAULT_JWT_SECRET),
        validation_alias="JWT_SECRET",
    )
    jwt_expire_minutes: int = Field(default=480, validation_alias="JWT_EXPIRE_MINUTES")

    admin_name: str = Field(default="System Admin", validation_alias="ADMIN_NAME")
    admin_username: str = Field(default="admin", validation_alias="ADMIN_USERNAME")
    admin_email: str = Field(default="admin@dairyfarm.com", validation_alias="ADMIN_EMAIL")
    admin_password: SecretStr = Field(
        default=SecretStr("ChangeMeImmediately123!"),
        validation_alias="ADMIN_PASSWORD",
    )

    api_v1_prefix: str = Field(default="/api/v1", validation_alias="API_V1_PREFIX")

    BODY_LIMIT_BYTES: ClassVar[int] = 1024 * 1024

    @field_validator("database_url", mode="before")
    @classmethod
    def _empty_database_url(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def is_production(self) -> bool:
        return self.node_env.strip().lower() == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def sqlalchemy_database_url(self) -> URL:
        raw = self.database_url.get_secret_value().strip() if self.database_url else ""
        if raw and raw.lower().startswith("mysql"):
            url = make_url(raw)
            return url.set(drivername="mysql+asyncmy")

        return URL.create(
            "mysql+asyncmy",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
            query={"charset": "utf8mb4"},
        )


settings = Settings()
