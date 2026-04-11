import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    GMAIL_QUERY: str = os.getenv("GMAIL_QUERY", "to:listserv@school.edu OR from:listserv@school.edu")
    TIMEZONE: str = os.getenv("TIMEZONE", "America/Los_Angeles")
    NIGHTLY_REPORT_HOUR: int = int(os.getenv("NIGHTLY_REPORT_HOUR", "21"))
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:////tmp/assignments.db")
    GMAIL_CREDENTIALS_FILE: str = os.getenv("GMAIL_CREDENTIALS_FILE", "credentials.json")
    GMAIL_TOKEN_FILE: str = os.getenv("GMAIL_TOKEN_FILE", "token.json")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    # Hard cap on messages fetched per sync (safety limit — covers a full semester)
    MAX_MESSAGES_PER_SYNC: int = int(os.getenv("MAX_MESSAGES_PER_SYNC", "2000"))
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")


config = Config()
