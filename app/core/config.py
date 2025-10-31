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
    database_url: str = Field(default="postgresql://trading_user:secure_password_123@localhost/trading_bot", env="DATABASE_URL")
    
    # Redis
    redis_url: str = Field(default="redis://localhost:6379", env="REDIS_URL")
    
    # Alpaca API (Legacy - for market data)
    alpaca_api_key: str = Field(default="", env="ALPACA_API_KEY")
    alpaca_secret_key: str = Field(default="", env="ALPACA_SECRET_KEY")
    alpaca_base_url: str = Field(default="https://paper-api.alpaca.markets", env="ALPACA_BASE_URL")
    alpaca_data_url: str = Field(default="https://data.alpaca.markets", env="ALPACA_DATA_URL")

    # Alpaca Broker API (for bracket orders with stop loss + take profit)
    alpaca_broker_api_url: str = Field(default="https://broker-api.sandbox.alpaca.markets", env="ALPACA_BROKER_API_URL")
    alpaca_broker_email: str = Field(default="", env="ALPACA_BROKER_EMAIL")
    alpaca_broker_password: str = Field(default="", env="ALPACA_BROKER_PASSWORD")
    alpaca_broker_account_id: str = Field(default="", env="ALPACA_BROKER_ACCOUNT_ID")
    
    # Risk Management
    max_risk_per_trade: float = Field(default=0.01, env="MAX_RISK_PER_TRADE")
    daily_loss_limit: float = Field(default=0.03, env="DAILY_LOSS_LIMIT")
    max_concurrent_positions: int = Field(default=5, env="MAX_CONCURRENT_POSITIONS")
    
    # Trading Schedule (Stock Market)
    market_open_time: str = Field(default="09:30", env="MARKET_OPEN_TIME")
    market_close_time: str = Field(default="15:55", env="MARKET_CLOSE_TIME")
    timezone: str = Field(default="America/New_York", env="TIMEZONE")
    
    # Crypto Trading Configuration (24/7 via Alpaca)
    crypto_trading_enabled: bool = Field(default=True, env="CRYPTO_TRADING_ENABLED")
    
    # Alpaca Crypto Portfolio Strategy (based on ~20 available cryptos)
    # Tier 1: BTC (40%) + ETH (30%) = 70% total
    crypto_btc_allocation: float = Field(default=0.40, env="CRYPTO_BTC_ALLOCATION")
    crypto_eth_allocation: float = Field(default=0.30, env="CRYPTO_ETH_ALLOCATION")
    
    # Tier 2: Top altcoins available on Alpaca - 25% total
    crypto_alts_allocation: float = Field(default=0.25, env="CRYPTO_ALTS_ALLOCATION")
    
    # Cash buffer in USDC - 5% total
    crypto_cash_allocation: float = Field(default=0.05, env="CRYPTO_CASH_ALLOCATION")
    
    # Rebalancing Configuration
    crypto_rebalance_threshold: float = Field(default=0.15, env="CRYPTO_REBALANCE_THRESHOLD")  # 15% deviation
    crypto_rebalance_check_hours: int = Field(default=6, env="CRYPTO_REBALANCE_CHECK_HOURS")
    crypto_max_positions: int = Field(default=8, env="CRYPTO_MAX_POSITIONS")
    
    # Semi-holding Strategy Configuration
    crypto_min_hold_days: int = Field(default=3, env="CRYPTO_MIN_HOLD_DAYS")
    crypto_max_hold_days: int = Field(default=30, env="CRYPTO_MAX_HOLD_DAYS")
    
    # Technical Analysis Parameters (optimized for crypto volatility)
    crypto_rsi_oversold: float = Field(default=25, env="CRYPTO_RSI_OVERSOLD")
    crypto_rsi_overbought: float = Field(default=75, env="CRYPTO_RSI_OVERBOUGHT")
    
    # Bot Selection
    active_bot_mode: str = Field(default="stock", env="ACTIVE_BOT_MODE")  # 'stock', 'crypto', 'both'
    
    model_config = {"env_file": ".env", "case_sensitive": False, "extra": "allow"}


# Create global settings instance
settings = Settings()