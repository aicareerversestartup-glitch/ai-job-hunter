"""Application settings, read from environment variables (and a .env file if present)."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if value[:1] in ('"', "'") and value[1:].find(value[0]) != -1:
            value = value[1:1 + value[1:].find(value[0])]
        else:
            value = value.split(" #", 1)[0].split("\t#", 1)[0].strip()  # inline comment
        os.environ.setdefault(key.strip(), value)


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


def _list(name: str, default: str = "") -> list[str]:
    return [v.strip() for v in os.getenv(name, default).split(",") if v.strip()]


@dataclass
class Settings:
    env: str = "development"
    app_name: str = "AI Job Hunter"
    database_url: str = ""
    secret_key: str = ""
    encryption_key: str = ""
    access_token_minutes: int = 60 * 12
    cors_origins: list[str] = field(default_factory=list)
    data_dir: Path = ROOT_DIR / "data"
    max_upload_mb: int = 10
    allow_registration: bool = True
    run_scheduler: bool = True
    discovery_interval_hours: int = 12
    # Default AI configuration (each user can override in Settings).
    ai_provider: str = "none"
    ai_model: str = ""
    ai_api_key: str = ""
    ai_base_url: str = ""
    # Optional job-source credentials.
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    jooble_api_key: str = ""
    # Interview email tracking
    inbox_check_minutes: int = 60
    # Browser automation.
    playwright_headless: bool = False
    allow_auto_submit: bool = False  # global kill-switch; user approval is still required per application
    http_user_agent: str = "AIJobHunter/1.0 (personal job-search assistant)"
    apply_assist_enabled: bool = True  # browser form-filling; only works where the app runs on the user's own computer
    # Public deployment
    public_url: str = "http://localhost:8000"
    operator_name: str = ""  # shown in Privacy Policy / Terms
    support_email: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    max_discoveries_per_day: int = 6
    max_drafts_per_day: int = 40
    # Advertising (off until IDs are set)
    ads_enabled: bool = False
    ads_test_mode: bool = True  # Google test ads; switch off only after your AdMob/AdSense accounts are approved
    adsense_client: str = ""  # ca-pub-XXXXXXXXXXXXXXXX
    adsense_slot_waiting: str = ""
    adsense_slot_feed: str = ""
    admob_banner_android: str = ""  # ca-app-pub-XXXX/YYYY
    admob_banner_ios: str = ""
    admob_rewarded_android: str = ""
    admob_rewarded_ios: str = ""
    # Plans
    free_drafts_per_day: int = 10
    free_searches_per_day: int = 3
    pro_searches_per_day: int = 12
    reward_ad_bonus: int = 5
    reward_ads_per_day: int = 2
    referral_pro_days: int = 7
    server_ai_for_free_users: bool = False  # the server's AI key costs money; by default only Pro uses it
    # RevenueCat (Apple, Google and web subscriptions)
    revenuecat_secret_key: str = ""  # server-side REST key (sk_...)
    revenuecat_webhook_auth: str = ""  # the Authorization header value you set in the RevenueCat dashboard
    revenuecat_public_ios: str = ""
    revenuecat_public_android: str = ""
    revenuecat_public_web: str = ""
    pro_entitlement: str = "pro"

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def generated_dir(self) -> Path:
        return self.data_dir / "generated"

    @property
    def master_cv_dir(self) -> Path:
        return self.data_dir / "master_cv"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_dotenv(ROOT_DIR / ".env")
    env = os.getenv("APP_ENV", "development")
    data_dir = Path(os.getenv("DATA_DIR", str(ROOT_DIR / "data"))).resolve()
    secret = os.getenv("SECRET_KEY", "")
    if not secret:
        if env == "production":
            raise RuntimeError("SECRET_KEY must be set in production.")
        secret_file = data_dir / ".dev_secret"
        data_dir.mkdir(parents=True, exist_ok=True)
        if not secret_file.exists():
            secret_file.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        secret = secret_file.read_text(encoding="utf-8").strip()
    settings = Settings(
        env=env,
        database_url=os.getenv("DATABASE_URL", f"sqlite:///{(data_dir / 'jobhunter.db').as_posix()}"),
        secret_key=secret,
        encryption_key=os.getenv("ENCRYPTION_KEY", ""),
        access_token_minutes=int(os.getenv("ACCESS_TOKEN_MINUTES", str(60 * 12))),
        # capacitor://localhost (iOS app) and https://localhost (Android app) are the native app origins.
        cors_origins=_list("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,capacitor://localhost,"
                                           "https://localhost,http://localhost"),
        data_dir=data_dir,
        max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "10")),
        allow_registration=_bool("ALLOW_REGISTRATION", True),
        run_scheduler=_bool("RUN_SCHEDULER", True),
        discovery_interval_hours=int(os.getenv("DISCOVERY_INTERVAL_HOURS", "12")),
        ai_provider=os.getenv("AI_PROVIDER", "none"),
        ai_model=os.getenv("AI_MODEL", ""),
        ai_api_key=os.getenv("AI_API_KEY", ""),
        ai_base_url=os.getenv("AI_BASE_URL", ""),
        adzuna_app_id=os.getenv("ADZUNA_APP_ID", ""),
        adzuna_app_key=os.getenv("ADZUNA_APP_KEY", ""),
        jooble_api_key=os.getenv("JOOBLE_API_KEY", ""),
        inbox_check_minutes=int(os.getenv("INBOX_CHECK_MINUTES", "60")),
        playwright_headless=_bool("PLAYWRIGHT_HEADLESS", False),
        allow_auto_submit=_bool("ALLOW_AUTO_SUBMIT", False),
        apply_assist_enabled=_bool("APPLY_ASSIST_ENABLED", not _bool("PLAYWRIGHT_HEADLESS", False)),
        public_url=os.getenv("PUBLIC_URL", "http://localhost:8000").rstrip("/"),
        operator_name=os.getenv("OPERATOR_NAME", ""),
        support_email=os.getenv("SUPPORT_EMAIL", ""),
        smtp_host=os.getenv("SMTP_HOST", ""),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_user=os.getenv("SMTP_USER", ""),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        smtp_from=os.getenv("SMTP_FROM", ""),
        max_discoveries_per_day=int(os.getenv("MAX_DISCOVERIES_PER_DAY", "6")),
        max_drafts_per_day=int(os.getenv("MAX_DRAFTS_PER_DAY", "40")),
        ads_enabled=_bool("ADS_ENABLED", False),
        ads_test_mode=_bool("ADS_TEST_MODE", True),
        adsense_client=os.getenv("ADSENSE_CLIENT", ""),
        adsense_slot_waiting=os.getenv("ADSENSE_SLOT_WAITING", ""),
        adsense_slot_feed=os.getenv("ADSENSE_SLOT_FEED", ""),
        admob_banner_android=os.getenv("ADMOB_BANNER_ANDROID", ""),
        admob_banner_ios=os.getenv("ADMOB_BANNER_IOS", ""),
        admob_rewarded_android=os.getenv("ADMOB_REWARDED_ANDROID", ""),
        admob_rewarded_ios=os.getenv("ADMOB_REWARDED_IOS", ""),
        free_drafts_per_day=int(os.getenv("FREE_DRAFTS_PER_DAY", "10")),
        free_searches_per_day=int(os.getenv("FREE_SEARCHES_PER_DAY", "3")),
        pro_searches_per_day=int(os.getenv("PRO_SEARCHES_PER_DAY", "12")),
        reward_ad_bonus=int(os.getenv("REWARD_AD_BONUS", "5")),
        reward_ads_per_day=int(os.getenv("REWARD_ADS_PER_DAY", "2")),
        referral_pro_days=int(os.getenv("REFERRAL_PRO_DAYS", "7")),
        server_ai_for_free_users=_bool("SERVER_AI_FOR_FREE_USERS", False),
        revenuecat_secret_key=os.getenv("REVENUECAT_SECRET_KEY", ""),
        revenuecat_webhook_auth=os.getenv("REVENUECAT_WEBHOOK_AUTH", ""),
        revenuecat_public_ios=os.getenv("REVENUECAT_PUBLIC_IOS", ""),
        revenuecat_public_android=os.getenv("REVENUECAT_PUBLIC_ANDROID", ""),
        revenuecat_public_web=os.getenv("REVENUECAT_PUBLIC_WEB", ""),
        pro_entitlement=os.getenv("PRO_ENTITLEMENT", "pro"),
    )
    for folder in (settings.uploads_dir, settings.generated_dir, settings.master_cv_dir):
        folder.mkdir(parents=True, exist_ok=True)
    return settings
