"""
Stock Screener: Simplified version without FMP fundamentals
Works with just Alpaca for price data
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import requests
import pandas as pd
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class StockAlert:
    """Stock alert data structure"""
    ticker: str
    current_price: float
    ath_5y: float
    ath_date: str
    drop_pct: float
    price_cagr_5y: float


class StockScreener:
    """Stock screening with Alpaca only"""

    def __init__(self):
        self.alpaca_key = os.getenv('ALPACA_API_KEY')
        self.alpaca_secret = os.getenv('ALPACA_SECRET_KEY')
        self.email_from = os.getenv('EMAIL_FROM')
        self.email_to = os.getenv('EMAIL_TO')
        self.email_password = os.getenv('EMAIL_PASSWORD')

        self.alpaca_data = "https://data.alpaca.markets"
        self.alpaca_headers = {
            "APCA-API-KEY-ID": self.alpaca_key,
            "APCA-API-SECRET-KEY": self.alpaca_secret
        }

    def get_sp500_symbols(self) -> List[str]:
        """Get stock symbols to screen"""
        return [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'TSLA', 'META', 'BRK.B',
            'V', 'UNH', 'JNJ', 'WMT', 'JPM', 'MA', 'PG', 'XOM', 'HD', 'CVX',
            'LLY', 'MRK', 'ABBV', 'KO', 'AVGO', 'PEP', 'COST', 'TMO', 'MCD',
            'CSCO', 'ABT', 'ACN', 'DHR', 'VZ', 'ADBE', 'TXN', 'NKE', 'NEE',
            'PM', 'DIS', 'CRM', 'WFC', 'BMY', 'ORCL', 'RTX', 'UPS', 'MS',
            'HON', 'QCOM', 'AMGN', 'IBM', 'LOW', 'INTU', 'GE', 'BA', 'AMD',
            'CAT', 'UNP', 'SBUX', 'SPGI', 'GS', 'AXP', 'BLK', 'LMT', 'DE'
        ]

    def get_5year_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """Get 5 years of daily price data from Alpaca"""
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=5*365 + 30)

            url = f"{self.alpaca_data}/v2/stocks/{symbol}/bars"
            params = {
                'timeframe': '1Day',
                'start': start_date.isoformat(),
                'end': end_date.isoformat(),
                'limit': 10000,
                'adjustment': 'split',
                'feed': 'sip'
            }

            response = requests.get(url, headers=self.alpaca_headers, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()
            if 'bars' not in data or not data['bars']:
                return None

            df = pd.DataFrame(data['bars'])
            df['t'] = pd.to_datetime(df['t'])
            df = df.set_index('t')

            return df

        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")
            return None

    def calculate_cagr(self, start_value: float, end_value: float, years: float) -> float:
        """Calculate Compound Annual Growth Rate"""
        if start_value <= 0 or end_value <= 0 or years <= 0:
            return 0.0
        return ((end_value / start_value) ** (1 / years) - 1) * 100

    def screen_stocks(self) -> List[StockAlert]:
        """Main screening logic"""
        alerts = []
        symbols = self.get_sp500_symbols()

        print(f"Screening {len(symbols)} stocks for 30%+ drops from 5-year ATH...")
        print()

        for symbol in symbols:
            try:
                df = self.get_5year_data(symbol)
                if df is None or len(df) < 100:
                    continue

                ath_5y = df['h'].max()
                ath_date = df['h'].idxmax()
                current_price = df['c'].iloc[-1]

                drop_pct = ((current_price - ath_5y) / ath_5y) * 100

                if drop_pct <= -30:
                    price_5y_ago = df['c'].iloc[0]
                    price_cagr_5y = self.calculate_cagr(price_5y_ago, current_price, 5)

                    alert = StockAlert(
                        ticker=symbol,
                        current_price=round(current_price, 2),
                        ath_5y=round(ath_5y, 2),
                        ath_date=ath_date.strftime('%Y-%m-%d'),
                        drop_pct=round(drop_pct, 2),
                        price_cagr_5y=round(price_cagr_5y, 2)
                    )

                    alerts.append(alert)
                    print(f"Found: {symbol}: {drop_pct:.1f}% from ATH")

            except Exception as e:
                print(f"Error processing {symbol}: {e}")
                continue

        alerts.sort(key=lambda x: x.drop_pct)
        return alerts

    def create_email_html(self, alerts: List[StockAlert]) -> str:
        """Create HTML email"""
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                h2 {{ color: #2c3e50; }}
                table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
                th {{ background-color: #3498db; color: white; padding: 12px; text-align: left; }}
                td {{ padding: 10px; border-bottom: 1px solid #ddd; }}
                tr:hover {{ background-color: #f5f5f5; }}
                .negative {{ color: #e74c3c; font-weight: bold; }}
                .positive {{ color: #27ae60; }}
            </style>
        </head>
        <body>
            <h2>Stock Alert: Deep Value Opportunities</h2>
            <p>Market Close: {datetime.now().strftime('%Y-%m-%d %H:%M ET')}</p>
            <p>Found <strong>{len(alerts)}</strong> stocks down 30%+ from 5-year ATH</p>

            <table>
                <thead>
                    <tr>
                        <th>Ticker</th>
                        <th>Current Price</th>
                        <th>5Y ATH</th>
                        <th>ATH Date</th>
                        <th>Drop %</th>
                        <th>5Y Price CAGR</th>
                    </tr>
                </thead>
                <tbody>
        """

        for alert in alerts:
            html += f"""
                <tr>
                    <td><strong>{alert.ticker}</strong></td>
                    <td>${alert.current_price}</td>
                    <td>${alert.ath_5y}</td>
                    <td>{alert.ath_date}</td>
                    <td class="negative">{alert.drop_pct}%</td>
                    <td class="{'positive' if alert.price_cagr_5y > 0 else 'negative'}">{alert.price_cagr_5y}%</td>
                </tr>
            """

        html += """
                </tbody>
            </table>

            <p style="margin-top: 30px; color: #7f8c8d; font-size: 12px;">
                Automated Stock Screener by Forja Analytics<br>
                Data source: Alpaca Markets
            </p>
        </body>
        </html>
        """

        return html

    def send_email(self, alerts: List[StockAlert]):
        """Send email alert"""
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"Stock Alert: {len(alerts)} Deep Value Opportunities - {datetime.now().strftime('%Y-%m-%d')}"
            msg['From'] = self.email_from
            msg['To'] = self.email_to

            html_content = self.create_email_html(alerts)
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)

            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(self.email_from, self.email_password)
                server.send_message(msg)

            print(f"\nEmail sent successfully to {self.email_to}")

        except Exception as e:
            print(f"Error sending email: {e}")

    def run(self):
        """Main execution"""
        print("="*60)
        print("Stock Screener - Deep Value Finder")
        print("="*60)
        print()

        alerts = self.screen_stocks()

        if alerts:
            print(f"\nFound {len(alerts)} stocks down 30%+ from 5-year ATH")
            self.send_email(alerts)
        else:
            print("\nNo stocks found matching criteria")

        print("\nScreener complete")
        print("="*60)


if __name__ == "__main__":
    screener = StockScreener()
    screener.run()
