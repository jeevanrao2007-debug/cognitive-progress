from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_ROOT_DIR = _BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            str(_BACKEND_DIR / ".env"),
            str(_ROOT_DIR / ".env"),
            ".env",
        ),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_name: str = Field(default="CognitiveProgress API", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_debug: bool = Field(default=True, alias="APP_DEBUG")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")
    frontend_origin: str = Field(default="http://127.0.0.1:5173", alias="FRONTEND_ORIGIN")

    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="cognitiveprogress", alias="POSTGRES_DB")
    postgres_user: str = Field(default="postgres", alias="POSTGRES_USER")
    postgres_password: str = Field(default="postgres", alias="POSTGRES_PASSWORD")
    ingestion_storage_path: str = Field(
        default="data/imports", alias="INGESTION_STORAGE_PATH"
    )

    ai_text_provider: str = Field(default="gemini", alias="AI_TEXT_PROVIDER")
    ai_embedding_provider: str = Field(default="sentence_transformers", alias="AI_EMBEDDING_PROVIDER")
    ai_text_model: str = Field(default="gemini-2.5-flash", alias="AI_TEXT_MODEL")
    ai_embedding_model: str = Field(default="all-MiniLM-L6-v2", alias="AI_EMBEDDING_MODEL")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")

    auto_accept_confidence_threshold: float = Field(
        default=0.9,
        alias="AUTO_ACCEPT_CONFIDENCE_THRESHOLD",
    )
    planner_review_confidence_threshold: float = Field(
        default=0.6,
        alias="PLANNER_REVIEW_CONFIDENCE_THRESHOLD",
    )

    matching_high_confidence_threshold: float = Field(default=0.70, alias="MATCHING_HIGH_CONFIDENCE_THRESHOLD")
    matching_ambiguous_score_delta: float = Field(default=0.08, alias="MATCHING_AMBIGUOUS_SCORE_DELTA")
    matching_no_match_threshold: float = Field(default=0.45, alias="MATCHING_NO_MATCH_THRESHOLD")
    matching_candidate_limit: int = Field(default=10, alias="MATCHING_CANDIDATE_LIMIT")

    reconciliation_auto_accept_threshold: float = Field(default=0.85, alias="RECONCILIATION_AUTO_ACCEPT_THRESHOLD")
    reconciliation_review_threshold: float = Field(default=0.50, alias="RECONCILIATION_REVIEW_THRESHOLD")
    reconciliation_no_decision_threshold: float = Field(default=0.30, alias="RECONCILIATION_NO_DECISION_THRESHOLD")
    reconciliation_freshness_half_life_days: float = Field(default=14, alias="RECONCILIATION_FRESHNESS_HALF_LIFE_DAYS")
    reliability_daily_report: float = Field(default=0.90, alias="RELIABILITY_DAILY_REPORT")
    reliability_contractor_spreadsheet: float = Field(default=0.75, alias="RELIABILITY_CONTRACTOR_SPREADSHEET")
    reliability_discipline_spreadsheet: float = Field(default=0.80, alias="RELIABILITY_DISCIPLINE_SPREADSHEET")
    reliability_site_diary: float = Field(default=0.65, alias="RELIABILITY_SITE_DIARY")
    reliability_manual_entry: float = Field(default=0.60, alias="RELIABILITY_MANUAL_ENTRY")

    database_url: str | None = Field(default="sqlite:///./cognitiveprogress.db", alias="DATABASE_URL")

    @property
    def postgres_dsn(self) -> str:
        if self.database_url:
            if self.database_url.startswith("sqlite:///./"):
                rel_path = self.database_url[len("sqlite:///./") :]
                abs_db_path = (_BACKEND_DIR / rel_path).resolve()
                return f"sqlite:///{abs_db_path}"
            return self.database_url
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
