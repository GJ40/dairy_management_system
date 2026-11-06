from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import (
    Field,
    SecretStr,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

BASE_DIR = Path(__file__).resolve().parents[2]

DEFAULT_JWT_SECRET = "dairy_dev_super_secret_jwt_key_at_least_32_chars_long"
DEFAULT_ADMIN_PASSWORD = "ChangeMeImmediately123!"
MIN_PRODUCTION_SECRET_LENGTH = 32

SameSite = Literal["lax", "strict", "none"]


class Settings(BaseSettings):
    """Application settings, loaded from `backend_py/.env` and the environment.

    Environment variables always win over `.env` values, which is what makes
    the file safe to commit as `.env.example` and override per machine.
    """

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    # --- Server ---------------------------------------------------------
    node_env: str = Field(default="development", validation_alias="NODE_ENV")
    port: int = Field(default=8000, validation_alias="PORT")
    tz: str = Field(default="Asia/Kolkata", validation_alias="TZ")
    cors_origins: str = Field(
        default="http://localhost:5173,http://localhost:3000",
        validation_alias="CORS_ORIGINS",
    )

    # --- Database -------------------------------------------------------
    database_url: SecretStr | None = Field(default=None, validation_alias="DATABASE_URL")
    db_dialect: str = Field(default="mysql", validation_alias="DB_DIALECT")
    db_host: str = Field(default="localhost", validation_alias="DB_HOST")
    db_port: int = Field(default=3307, validation_alias="DB_PORT")
    db_name: str = Field(default="dairy_db", validation_alias="DB_NAME")
    db_user: str = Field(default="root", validation_alias="DB_USER")
    db_password: SecretStr = Field(default=SecretStr("root"), validation_alias="DB_PASSWORD")
    db_logging: bool = Field(default=False, validation_alias="DB_LOGGING")

    # --- Auth tokens ----------------------------------------------------
    jwt_secret: SecretStr = Field(
        default=SecretStr(DEFAULT_JWT_SECRET),
        validation_alias="JWT_SECRET",
    )
    access_token_expire_minutes: int = Field(
        default=30,
        ge=1,
        validation_alias="ACCESS_TOKEN_EXPIRE_MINUTES",
    )
    refresh_token_expire_minutes: int = Field(
        default=480,
        ge=1,
        validation_alias="REFRESH_TOKEN_EXPIRE_MINUTES",
    )

    # --- Customer portal auth -------------------------------------------
    customer_jwt_secret: SecretStr | None = Field(
        default=None,
        validation_alias="CUSTOMER_JWT_SECRET",
    )
    customer_activation_ttl_hours: int = Field(
        default=72,
        ge=1,
        validation_alias="CUSTOMER_ACTIVATION_TTL_HOURS",
    )
    customer_refresh_cookie_name: str = Field(
        default="dairy_customer_refresh_token",
        validation_alias="CUSTOMER_REFRESH_COOKIE_NAME",
    )
    customer_session_hint_cookie_name: str = Field(
        default="dairy_customer_session",
        validation_alias="CUSTOMER_SESSION_HINT_COOKIE_NAME",
    )

    # --- Customer orders ------------------------------------------------
    customer_order_min_litres: Decimal = Field(
        default=Decimal("1.00"),
        gt=0,
        validation_alias="CUSTOMER_ORDER_MIN_LITRES",
    )
    customer_order_max_litres: Decimal = Field(
        default=Decimal("500.00"),
        gt=0,
        validation_alias="CUSTOMER_ORDER_MAX_LITRES",
    )
    customer_order_daily_cap_litres: Decimal = Field(
        default=Decimal("500.00"),
        gt=0,
        validation_alias="CUSTOMER_ORDER_DAILY_CAP_LITRES",
    )
    customer_order_window_days: int = Field(
        default=14,
        ge=0,
        validation_alias="CUSTOMER_ORDER_WINDOW_DAYS",
    )

    # --- Email / SMTP ---------------------------------------------------
    frontend_url: str = Field(
        default="http://localhost:5173",
        validation_alias="FRONTEND_URL",
    )
    smtp_host: str = Field(default="", validation_alias="SMTP_HOST")
    smtp_port: int = Field(default=587, ge=1, le=65535, validation_alias="SMTP_PORT")
    smtp_user: str = Field(default="", validation_alias="SMTP_USER")
    smtp_password: SecretStr = Field(
        default=SecretStr(""),
        validation_alias="SMTP_PASSWORD",
    )
    smtp_use_tls: bool = Field(default=True, validation_alias="SMTP_USE_TLS")
    smtp_use_ssl: bool = Field(default=False, validation_alias="SMTP_USE_SSL")
    smtp_timeout_seconds: int = Field(
        default=10,
        ge=1,
        le=120,
        validation_alias="SMTP_TIMEOUT_SECONDS",
    )
    mail_from_email: str = Field(
        default="no-reply@dairyfarm.com",
        validation_alias="MAIL_FROM_EMAIL",
    )
    mail_from_name: str = Field(
        default="AmritDhara Dairy",
        validation_alias="MAIL_FROM_NAME",
    )
    email_settings_encryption_key: SecretStr | None = Field(
        default=None,
        validation_alias="EMAIL_SETTINGS_ENCRYPTION_KEY",
    )
    email_settings_encryption_key_previous: SecretStr | None = Field(
        default=None,
        validation_alias="EMAIL_SETTINGS_ENCRYPTION_KEY_PREVIOUS",
    )

    # --- Password reset -------------------------------------------------
    password_reset_ttl_minutes: int = Field(
        default=30,
        ge=5,
        le=1440,
        validation_alias="PASSWORD_RESET_TTL_MINUTES",
    )

    # --- Refresh cookie -------------------------------------------------
    refresh_cookie_name: str = Field(
        default="dairy_refresh_token",
        validation_alias="REFRESH_COOKIE_NAME",
    )
    # Must cover every guarded route: `get_current_user` rejects a request whose
    # access token is fine but whose refresh cookie is absent, and a browser
    # only sends the cookie to paths under this prefix.
    refresh_cookie_path: str = Field(
        default="/api/v1",
        validation_alias="REFRESH_COOKIE_PATH",
    )
    refresh_cookie_domain: str | None = Field(
        default=None,
        validation_alias="REFRESH_COOKIE_DOMAIN",
    )
    refresh_cookie_samesite: SameSite = Field(
        default="lax",
        validation_alias="REFRESH_COOKIE_SAMESITE",
    )
    # `None` means "secure in production, plain HTTP locally".
    refresh_cookie_secure: bool | None = Field(
        default=None,
        validation_alias="REFRESH_COOKIE_SECURE",
    )
    # Readable, secret-free flag the SPA checks before probing /auth/refresh, so
    # a first-time visitor does not trigger a guaranteed 401.
    session_hint_cookie_name: str = Field(
        default="dairy_session",
        validation_alias="SESSION_HINT_COOKIE_NAME",
    )

    # --- Bootstrap admin ------------------------------------------------
    admin_name: str = Field(default="System Admin", validation_alias="ADMIN_NAME")
    admin_username: str = Field(default="admin", validation_alias="ADMIN_USERNAME")
    admin_email: str = Field(default="admin@dairyfarm.com", validation_alias="ADMIN_EMAIL")
    admin_password: SecretStr = Field(
        default=SecretStr(DEFAULT_ADMIN_PASSWORD),
        validation_alias="ADMIN_PASSWORD",
    )

    # --- Security audit -------------------------------------------------
    # Honouring X-Forwarded-For without a trusted proxy lets any client spoof
    # its address, so this stays off until the deployment opts in.
    trust_proxy: bool = Field(default=False, validation_alias="TRUST_PROXY")
    audit_retention_days: int = Field(
        default=365,
        ge=30,
        le=3650,
        validation_alias="AUDIT_RETENTION_DAYS",
    )

    # --- Failed-login alerts -------------------------------------------
    failed_login_alert_enabled: bool = Field(
        default=True,
        validation_alias="FAILED_LOGIN_ALERT_ENABLED",
    )
    failed_login_alert_threshold: int = Field(
        default=5,
        ge=1,
        le=100,
        validation_alias="FAILED_LOGIN_ALERT_THRESHOLD",
    )
    failed_login_alert_window_minutes: int = Field(
        default=15,
        ge=1,
        le=1440,
        validation_alias="FAILED_LOGIN_ALERT_WINDOW_MINUTES",
    )
    failed_login_alert_cooldown_minutes: int = Field(
        default=15,
        ge=1,
        le=10080,
        validation_alias="FAILED_LOGIN_ALERT_COOLDOWN_MINUTES",
    )

    # --- Login lockout --------------------------------------------------
    # Temporary cooldown: after this many failures the account is refused for
    # `login_cooldown_minutes` and the owner is emailed. The clock starts on the
    # attempt that reaches the threshold, so the pause always lasts the full
    # duration. Attempts during the cooldown are refused and never counted, so
    # they cannot escalate into a lock. A burst that started a cooldown is
    # therefore given `login_lockout_window_minutes + login_cooldown_minutes`
    # before it expires.
    login_cooldown_threshold: int = Field(
        default=5,
        ge=2,
        le=100,
        validation_alias="LOGIN_COOLDOWN_THRESHOLD",
    )
    login_cooldown_minutes: int = Field(
        default=5,
        ge=1,
        le=1440,
        validation_alias="LOGIN_COOLDOWN_MINUTES",
    )
    # Hard lock: reaching this many counted failures deactivates the account
    # until an administrator unlocks it. The lock has no expiry of its own.
    login_lockout_threshold: int = Field(
        default=10,
        ge=2,
        le=1000,
        validation_alias="LOGIN_LOCKOUT_THRESHOLD",
    )
    # Counting window only: how far back a burst of failures is measured. It
    # never expires a lock, which lasts until an administrator clears it.
    login_lockout_window_minutes: int = Field(
        default=15,
        ge=1,
        le=1440,
        validation_alias="LOGIN_LOCKOUT_WINDOW_MINUTES",
    )

    # --- Server limits --------------------------------------------------
    api_v1_prefix: str = Field(default="/api/v1", validation_alias="API_V1_PREFIX")
    body_limit_bytes: int = Field(
        default=1024 * 1024,
        ge=1024,
        validation_alias="BODY_LIMIT_BYTES",
    )
    bcrypt_rounds: int = Field(default=10, ge=4, le=16, validation_alias="BCRYPT_ROUNDS")

    # --- Connection pool ------------------------------------------------
    db_pool_size: int = Field(default=10, ge=1, validation_alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=0, ge=0, validation_alias="DB_MAX_OVERFLOW")
    db_pool_timeout: int = Field(default=30, ge=1, validation_alias="DB_POOL_TIMEOUT")
    db_pool_recycle: int = Field(default=1800, ge=1, validation_alias="DB_POOL_RECYCLE")

    @model_validator(mode="after")
    def _normalize_smtp_host(self) -> "Settings":
        """Accept a pasted SMTP URL/`host:port` in `SMTP_HOST`.

        Common misconfiguration: pasting `smtp://localhost:1025` or the
        Mailpit web-UI URL into `SMTP_HOST`. Left as-is, `getaddrinfo` fails
        because the scheme is not part of a hostname. Strip the scheme/path
        and keep any explicit port.
        """
        raw = (self.smtp_host or "").strip()
        if not raw:
            self.smtp_host = ""
            return self
        if "://" in raw:
            raw = raw.split("://", 1)[1]
        raw = raw.split("/", 1)[0].strip()

        host, port = raw, None
        if raw.count(":") == 1 and not raw.startswith("["):
            candidate_host, _, candidate_port = raw.partition(":")
            if candidate_port.isdigit() and 1 <= int(candidate_port) <= 65535:
                host, port = candidate_host, int(candidate_port)

        self.smtp_host = host.strip()
        if port is not None:
            self.smtp_port = port
        return self

    @model_validator(mode="after")
    def _widen_refresh_cookie_path(self) -> "Settings":
        """Keep the session cookie visible to every guarded route.

        `get_current_user` rejects any request without this cookie, so a path
        narrower than the API — the old `/api/v1/auth` default, which browsers
        do not send to `/api/v1/customers` and friends — would 401 every other
        endpoint. Such a value is widened to the API prefix rather than
        silently locking the whole API.
        """
        path = (self.refresh_cookie_path or "").strip()
        if not path.startswith("/"):
            path = f"/{path}"
        path = path.rstrip("/") or "/"

        prefix = (self.api_v1_prefix or "").strip().rstrip("/") or "/"
        covers = path == "/" or path == prefix or prefix.startswith(f"{path}/")
        self.refresh_cookie_path = path if covers else prefix
        return self

    @model_validator(mode="after")
    def _guard_production_secrets(self) -> "Settings":
        """Refuse to boot production with development defaults.

        The repo ships working defaults so local setup is frictionless, which
        also means a copy-pasted `.env` can reach a real deployment: the JWT
        secret is public and the admin password is known. In production those
        values, and a shared staff/customer signing key, are fatal and are
        rejected at startup instead of silently accepted.
        """
        if not self.is_production:
            return self

        problems: list[str] = []
        jwt_secret = self.jwt_secret.get_secret_value()
        if (
            jwt_secret == DEFAULT_JWT_SECRET
            or len(jwt_secret) < MIN_PRODUCTION_SECRET_LENGTH
        ):
            problems.append(
                f"JWT_SECRET must be a private value of at least "
                f"{MIN_PRODUCTION_SECRET_LENGTH} characters"
            )

        customer_secret = (
            self.customer_jwt_secret.get_secret_value()
            if self.customer_jwt_secret is not None
            else ""
        )
        if not customer_secret:
            problems.append(
                "CUSTOMER_JWT_SECRET must be set so staff and customer tokens "
                "cannot be signed with the same key"
            )
        elif len(customer_secret) < MIN_PRODUCTION_SECRET_LENGTH:
            problems.append(
                f"CUSTOMER_JWT_SECRET must be at least "
                f"{MIN_PRODUCTION_SECRET_LENGTH} characters"
            )
        elif customer_secret == jwt_secret:
            problems.append("CUSTOMER_JWT_SECRET must differ from JWT_SECRET")

        if self.admin_password.get_secret_value() in ("", DEFAULT_ADMIN_PASSWORD):
            problems.append("ADMIN_PASSWORD must be changed from its default value")

        frontend = urlparse(self.frontend_base_url)
        frontend_host = (frontend.hostname or "").lower()
        if (
            frontend.scheme != "https"
            or not frontend_host
            or frontend_host in {"localhost", "127.0.0.1", "::1"}
        ):
            # Reset/activation links carry live tokens; a localhost or plain
            # HTTP URL would make them unusable and expose the token in transit.
            problems.append(
                "FRONTEND_URL must be the public https origin used in emailed links"
            )

        if problems:
            raise ValueError(
                "Unsafe production configuration: " + "; ".join(problems)
            )
        return self

    @field_validator("database_url", mode="before")
    @classmethod
    def _empty_database_url(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("customer_jwt_secret", mode="before")
    @classmethod
    def _empty_customer_jwt_secret(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator(
        "email_settings_encryption_key",
        "email_settings_encryption_key_previous",
        mode="before",
    )
    @classmethod
    def _empty_email_settings_key(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("refresh_cookie_domain", mode="before")
    @classmethod
    def _empty_cookie_domain(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("refresh_cookie_samesite", mode="before")
    @classmethod
    def _normalize_samesite(cls, value: object) -> object:
        if isinstance(value, str):
            text = value.strip().lower()
            return text or "lax"
        return value

    @field_validator("smtp_use_tls", "smtp_use_ssl", mode="before")
    @classmethod
    def _empty_smtp_flag(cls, value: object, info: ValidationInfo) -> object:
        if isinstance(value, str) and not value.strip():
            return info.field_name == "smtp_use_tls"
        return value

    @field_validator("frontend_url")
    @classmethod
    def _strip_frontend_url(cls, value: str) -> str:
        return value.strip().rstrip("/")

    @field_validator("refresh_cookie_secure", mode="before")
    @classmethod
    def _empty_cookie_secure(cls, value: object) -> object:
        if isinstance(value, str):
            text = value.strip().lower()
            if not text:
                return None
            if text in {"1", "true", "yes", "on"}:
                return True
            if text in {"0", "false", "no", "off"}:
                return False
        return value

    @property
    def is_production(self) -> bool:
        return self.node_env.strip().lower() == "production"

    @property
    def frontend_base_url(self) -> str:
        """Origin the SPA is served from, used to build emailed links."""
        url = (self.frontend_url or "").strip().rstrip("/")
        return url or "http://localhost:5173"

    @property
    def mail_enabled(self) -> bool:
        return bool(self.smtp_host.strip() and self.mail_from_email.strip())

    @property
    def cors_origin_list(self) -> list[str]:
        """Origins allowed to call the API, taken from `CORS_ORIGINS`.

        The trailing slash is dropped: browsers put the bare origin in the
        `Origin` header, so a configured `http://localhost:5173/` would never
        match and every preflight from that page would be rejected.
        """
        return [
            origin.rstrip("/")
            for origin in (part.strip() for part in self.cors_origins.split(","))
            if origin
        ]

    @property
    def refresh_cookie_max_age(self) -> int:
        return self.refresh_token_expire_minutes * 60

    @property
    def cookie_secure(self) -> bool:
        """Secure flag shared by every auth cookie."""
        # SameSite=None is only honoured by browsers on secure cookies.
        secure = (
            self.is_production
            if self.refresh_cookie_secure is None
            else self.refresh_cookie_secure
        )
        if self.refresh_cookie_samesite == "none":
            secure = True
        return secure

    @property
    def refresh_cookie_flags(self) -> dict[str, object]:
        """Cookie attributes shared by login, refresh and logout."""
        return {
            "key": self.refresh_cookie_name,
            "path": self.refresh_cookie_path,
            "domain": self.refresh_cookie_domain,
            "httponly": True,
            "secure": self.cookie_secure,
            "samesite": self.refresh_cookie_samesite,
        }

    @property
    def session_hint_cookie_flags(self) -> dict[str, object]:
        """Attributes of the non-httpOnly "a session may exist" flag cookie.

        It carries no secret (`1` when a refresh cookie was issued), so it is
        safe for the frontend bundle to read it.
        """
        return {
            "key": self.session_hint_cookie_name,
            "path": "/",
            "domain": self.refresh_cookie_domain,
            "httponly": False,
            "secure": self.cookie_secure,
            "samesite": self.refresh_cookie_samesite,
        }

    @property
    def customer_jwt_secret_value(self) -> str:
        if self.customer_jwt_secret is not None:
            return self.customer_jwt_secret.get_secret_value()
        return self.jwt_secret.get_secret_value()

    @property
    def customer_cookie_path(self) -> str:
        path = (self.api_v1_prefix or "").strip().rstrip("/")
        return path if path.startswith("/") else f"/{path}" if path else "/"

    @property
    def customer_refresh_cookie_max_age(self) -> int:
        return self.refresh_token_expire_minutes * 60

    @property
    def customer_refresh_cookie_flags(self) -> dict[str, object]:
        return {
            "key": self.customer_refresh_cookie_name,
            "path": self.customer_cookie_path,
            "domain": self.refresh_cookie_domain,
            "httponly": True,
            "secure": self.cookie_secure,
            "samesite": self.refresh_cookie_samesite,
        }

    @property
    def customer_session_hint_cookie_flags(self) -> dict[str, object]:
        return {
            "key": self.customer_session_hint_cookie_name,
            "path": "/",
            "domain": self.refresh_cookie_domain,
            "httponly": False,
            "secure": self.cookie_secure,
            "samesite": self.refresh_cookie_samesite,
        }

    @property
    def jwt_expire_minutes(self) -> int:
        """Backwards-compatible alias for the access-token lifetime."""
        return self.access_token_expire_minutes

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
