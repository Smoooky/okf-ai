"""Wheelo settings, read from environment variables."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("WHEELO_DATABASE_URL", "postgresql://localhost:5432/wheelo")
    jwt_secret: str = os.getenv("WHEELO_JWT_SECRET", "dev-secret-change-me")
    payments_api_url: str = os.getenv("WHEELO_PAYMENTS_URL", "https://sandbox.payments.example")
    sms_gateway_url: str = os.getenv("WHEELO_SMS_URL", "http://localhost:8025")


settings = Settings()
