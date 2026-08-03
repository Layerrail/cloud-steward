from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Cloud Steward"
    app_env: str = "development"
    database_url: str = "sqlite:///./var/cloud-steward.db"
    gemini_api_key: str | None = Field(default=None, repr=False)
    gemini_model: str = "gemini-3.6-flash"
    google_cloud_project: str | None = None
    google_cloud_location: str = "global"
    google_genai_use_vertexai: bool = False
    datahub_mcp_url: str | None = None
    datahub_gms_url: str | None = None
    datahub_gms_token: str | None = Field(default=None, repr=False)
    datahub_search_tool: str | None = None
    layerrail_api_url: str = "https://api.layerrail.com"
    layerrail_api_token: str | None = Field(default=None, repr=False)
    require_approval: bool = True
    allow_mutations: bool = False
    static_dir: Path = Path(__file__).parent / "static"

    @property
    def gemini_enabled(self) -> bool:
        return bool(
            self.gemini_api_key
            or (self.google_genai_use_vertexai and self.google_cloud_project)
        )

    @property
    def datahub_enabled(self) -> bool:
        return bool(self.datahub_mcp_url or self.datahub_gms_url)


@lru_cache

def get_settings() -> Settings:
    return Settings()
