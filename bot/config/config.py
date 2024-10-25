from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)

    API_ID: int
    API_HASH: str

    PLAY_INTRO: bool = True

    USE_REF: bool = True
    REF_ID: str = "f773211512"  # It would be great if you didn't change it, but I'm not stopping you

    INITIAL_START_DELAY_SECONDS: list[int] = [10, 240]  # in seconds

    SLEEP_INTERVAL_MINUTES: list[int] = [60, 120]  # in minutes

    SLEEP_AT_NIGHT: bool = True
    NIGHT_START_HOURS: list[int] = [0, 2]  # 24 hour format in your timezone
    NIGHT_END_HOURS: list[int] = [6, 8]  # 24 hour format in your timezone
    ADDITIONAL_NIGHT_SLEEP_MINUTES: list[int] = [2, 45]  # in minutes

    CLAIM_PX: bool = True
    UPGRADE_BOOSTS: bool = True


settings = Settings()  # type: ignore
