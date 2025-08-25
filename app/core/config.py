"""
Configuration management for the trading bot.
Loads environment variables and provides application settings.
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Application
    app_name: str = Field(default="Trading Bot", env="APP_NAME")
    app_version: str = Field(default="1.0.0", env="APP_VERSION")
    debug: bool = Field(default=False, env="DEBUG")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    
    # Database
    database_url: str = Field(env="DATABASE_URL")
    
    # Redis
    redis_url: str = Field(env="REDIS_URL")
    
    # Alpaca API
    alpaca_api_key: str = Field(env="ALPACA_API_KEY")
    alpaca_secret_key: str = Field(env="ALPACA_SECRET_KEY")
    alpaca_base_url: str = Field(env="ALPACA_BASE_URL")
    alpaca_data_url: str = Field(env="ALPACA_DATA_URL")
    
    # Risk Management
    max_risk_per_trade: float = Field(default=0.01, env="MAX_RISK_PER_TRADE")
    daily_loss_limit: float = Field(default=0.03, env="DAILY_LOSS_LIMIT")
    max_concurrent_positions: int = Field(default=5, env="MAX_CONCURRENT_POSITIONS")
    
    # Trading Schedule
    market_open_time: str = Field(default="09:30", env="MARKET_OPEN_TIME")
    market_close_time: str = Field(default="15:55", env="MARKET_CLOSE_TIME")
    timezone: str = Field(default="America/New_York", env="TIMEZONE")
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Create global settings instance
settings = Settings()