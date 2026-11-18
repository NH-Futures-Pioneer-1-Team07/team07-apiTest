"""설정. backend/.env 또는 환경변수에서 읽는다."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent

BASE_URLS = {"mock": "https://apidemo.futures.co.kr", "real": "https://api.futures.co.kr"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    nh_env: Literal["mock", "real"] = "mock"
    nh_app_key: SecretStr | None = None
    nh_app_secret: SecretStr | None = None
    nh_overseas_app_key: SecretStr | None = None
    nh_overseas_app_secret: SecretStr | None = None

    # NH 명세 폴더. 엑셀(*.xlsx)이 있으면 엑셀을, 없으면 apis/*.md 를 읽는다
    nh_docs_dir: Path = REPO_DIR / "docs" / "nh-api"
    cases_dir: Path = REPO_DIR / "testcases" / "nh-futures"
    issues_dir: Path = REPO_DIR / "issues" / "nh-futures"
    db_path: Path = BACKEND_DIR / "data" / "runs.sqlite3"

    allow_real_orders: bool = False
    team: str = "team-07"

    @property
    def base_url(self) -> str:
        return BASE_URLS[self.nh_env]

    def resolve(self, path: Path) -> Path:
        return path if path.is_absolute() else (BACKEND_DIR / path).resolve()


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.nh_docs_dir = s.resolve(s.nh_docs_dir)
    s.cases_dir = s.resolve(s.cases_dir)
    s.issues_dir = s.resolve(s.issues_dir)
    s.db_path = s.resolve(s.db_path)
    return s
