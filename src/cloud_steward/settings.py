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
    llama_cpp_binary: str | None = None
    llama_cpp_model_path: str | None = None
    llama_cpp_model_name: str = "Qwen2.5-0.5B-Instruct Q4_0"
    llama_cpp_threads: int = Field(default=4, ge=1, le=128)
    llama_cpp_context_size: int = Field(default=4096, ge=512, le=32768)
    llama_cpp_max_tokens: int = Field(default=768, ge=128, le=4096)
    llama_cpp_timeout_seconds: int = Field(default=300, ge=10, le=1800)
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
    def llama_cpp_enabled(self) -> bool:
        return bool(self.llama_cpp_binary and self.llama_cpp_model_path)

    @property
    def datahub_enabled(self) -> bool:
        return bool(self.datahub_mcp_url or self.datahub_gms_url)


@lru_cache

def get_settings() -> Settings:
    return Settings()
