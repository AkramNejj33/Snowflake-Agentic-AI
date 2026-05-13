"""Application configuration — loaded from environment variables."""

import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from pydantic import Field

_root = Path(__file__).parent.parent
load_dotenv(_root / ".env")


class SnowflakeSettings(BaseSettings):
    account: str   = Field(..., alias="SNOWFLAKE_ACCOUNT")
    user: str      = Field(..., alias="SNOWFLAKE_USER")
    password: str  = Field(..., alias="SNOWFLAKE_PASSWORD")
    database: str  = Field("AGENTIC_DB",   alias="SNOWFLAKE_DATABASE")
    schema_: str   = Field("RAW",          alias="SNOWFLAKE_SCHEMA")
    warehouse: str = Field("AGENTIC_WH",   alias="SNOWFLAKE_WAREHOUSE")
    role: str      = Field("AGENTIC_ROLE", alias="SNOWFLAKE_ROLE")

    model_config = {"populate_by_name": True, "extra": "ignore", "env_file": str(_root / ".env")}


class GoogleSettings(BaseSettings):
    api_key: str = Field(..., alias="GOOGLE_API_KEY")
    model: str   = Field("gemini-2.0-flash", alias="GEMINI_MODEL")

    model_config = {"populate_by_name": True, "extra": "ignore", "env_file": str(_root / ".env")}


class AppSettings(BaseSettings):
    env: str       = Field("development", alias="APP_ENV")
    log_level: str = Field("INFO",        alias="LOG_LEVEL")
    api_port: int  = Field(8000,          alias="API_PORT")
    ui_port: int   = Field(8501,          alias="UI_PORT")

    chroma_persist_dir: str = Field("./data/chroma",       alias="CHROMA_PERSIST_DIR")
    agent_state_dir: str    = Field("./data/agent_states", alias="AGENT_STATE_DIR")

    model_config = {"populate_by_name": True, "extra": "ignore", "env_file": str(_root / ".env")}


class Settings:
    def __init__(self) -> None:
        self.snowflake = SnowflakeSettings()
        self.google    = GoogleSettings()
        self.app       = AppSettings()

        for d in [self.app.chroma_persist_dir, self.app.agent_state_dir]:
            Path(d).mkdir(parents=True, exist_ok=True)


settings = Settings()
