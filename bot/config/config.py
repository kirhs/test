from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)

    API_ID: int
    API_HASH: str

    USE_REF: bool = True
    REF_ID: str = "f773211512"  # It would be great if you didn't change it, but I'm not stopping you

    START_DELAY: list[int] = [10, 240]  # in seconds
    SLEEP_TIME: list[int] = [60, 120]  # in minutes

    SLEEP_AT_NIGHT: bool = True
    NIGHT_START: list[int] = [0, 2]  # 24 hour format in your timezone
    NIGHT_END: list[int] = [8, 10]  # 24 hour format in your timezone
    RANDOM_MINUTES_TO_SLEEP_TIME: list[int] = [2, 30]  # in minutes


settings = Settings()  # type: ignore
