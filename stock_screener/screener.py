"""
Stock Screener: Finds stocks down 30%+ from 5-year ATH
Clean version - no fundamentals, working email
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from typing import List, Optional
import requests
import pandas as pd
from dataclasses import dataclass
from dotenv import load_dotenv
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content

# Load environment variables from .env file
load_dotenv()


@dataclass
class StockAlert:
    """Stock alert data structure"""
    ticker: str
    current_price: float
    ath_5y: float
    ath_date: str
    drop_pct: float
    price_cagr_5y: Optional[float] = None


class StockScreener:
    """Main stock screening class"""

    def __init__(self):
        # API Keys from environment
        self.alpaca_key = os.getenv('ALPACA_API_KEY')
        self.alpaca_secret = os.getenv('ALPACA_SECRET_KEY')
        self.fmp_key = os.getenv('FMP_API_KEY')

        # Email config
        self.email_from = os.getenv('EMAIL_FROM')
        self.email_to = os.getenv('EMAIL_TO')
        self.email_password = os.getenv('EMAIL_PASSWORD')  # For SMTP fallback
        self.sendgrid_api_key = os.getenv('SENDGRID_API_KEY')

        # Check if email is configured (prefer SendGrid, fallback to SMTP)
        self.use_sendgrid = bool(self.sendgrid_api_key and self.email_from and self.email_to)
        self.use_smtp = bool(self.email_from and self.email_to and self.email_password)
        self.email_configured = self.use_sendgrid or self.use_smtp

        if not self.email_configured:
            print("WARNING: Email not configured. Set SENDGRID_API_KEY (recommended) or EMAIL_FROM, EMAIL_TO, EMAIL_PASSWORD")

        # API endpoints
        self.alpaca_data = "https://data.alpaca.markets"
        self.fmp_base = "https://financialmodelingprep.com/api/v3"

        # Headers for Alpaca
        self.alpaca_headers = {
            "APCA-API-KEY-ID": self.alpaca_key,
            "APCA-API-SECRET-KEY": self.alpaca_secret
        }

    def get_nasdaq_nyse_symbols(self) -> List[str]:
        """Get curated list: NASDAQ-100 + S&P 500 + Top Penny Stocks"""
        print("Loading curated stock list: NASDAQ-100, S&P 500, and Top 100 Penny Stocks...")

        # NASDAQ-100 (top 100 non-financial NASDAQ stocks)
        nasdaq_100 = [
            'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'NVDA', 'TSLA', 'META', 'AVGO', 'COST',
            'ASML', 'NFLX', 'ADBE', 'AMD', 'PEP', 'CSCO', 'TMUS', 'LIN', 'CMCSA', 'INTC',
            'INTU', 'TXN', 'QCOM', 'AMAT', 'AMGN', 'HON', 'BKNG', 'ISRG', 'PANW', 'VRTX',
            'ADP', 'ADI', 'SBUX', 'GILD', 'MU', 'LRCX', 'REGN', 'MDLZ', 'KLAC', 'PYPL',
            'SNPS', 'CDNS', 'MELI', 'CTAS', 'MAR', 'CRWD', 'MRVL', 'ORLY', 'CSX', 'ADSK',
            'DASH', 'FTNT', 'ABNB', 'ROP', 'WDAY', 'PCAR', 'NXPI', 'CPRT', 'AEP', 'MNST',
            'PAYX', 'ROST', 'FAST', 'ODFL', 'KDP', 'EA', 'BKR', 'VRSK', 'CTSH', 'DDOG',
            'EXC', 'GEHC', 'TEAM', 'IDXX', 'CSGP', 'KHC', 'CCEP', 'ZS', 'ON', 'ANSS',
            'DXCM', 'TTWO', 'BIIB', 'CDW', 'MDB', 'XEL', 'ILMN', 'GFS', 'WBD', 'FANG',
            'MRNA', 'ARM', 'DLTR', 'WBA', 'SMCI', 'ALGN', 'RIVN', 'LCID', 'ZM', 'SIRI'
        ]

        # S&P 500 major stocks (top 100 by market cap - non-NASDAQ to avoid duplicates)
        sp500_nyse = [
            'JPM', 'JNJ', 'V', 'UNH', 'WMT', 'MA', 'PG', 'HD', 'XOM', 'CVX',
            'LLY', 'ABBV', 'MRK', 'KO', 'BAC', 'TMO', 'ORCL', 'ABT', 'CRM', 'ACN',
            'NFLX', 'MCD', 'NKE', 'DHR', 'ADBE', 'DIS', 'TXN', 'VZ', 'WFC', 'NOW',
            'PM', 'CMCSA', 'BMY', 'NEE', 'RTX', 'UNP', 'MS', 'SPGI', 'LOW', 'LIN',
            'GS', 'UPS', 'T', 'ELV', 'BLK', 'HON', 'SCHW', 'CAT', 'AXP', 'DE',
            'AMAT', 'SYK', 'PLD', 'BKNG', 'CI', 'LRCX', 'GILD', 'VRTX', 'MDLZ', 'ADI',
            'AMT', 'REGN', 'TJX', 'CB', 'SO', 'MMC', 'ISRG', 'PGR', 'SBUX', 'DUK',
            'ZTS', 'EQIX', 'BDX', 'PH', 'ETN', 'AON', 'ITW', 'SHW', 'APD', 'CME',
            'GE', 'CL', 'BSX', 'MCO', 'MMM', 'FIS', 'USB', 'PNC', 'HUM', 'C',
            'MO', 'WM', 'FCX', 'TGT', 'NSC', 'COP', 'SLB', 'EMR', 'EOG', 'NOC'
        ]

        # Top 100 Penny Stocks (popular stocks under $5)
        penny_stocks = [
            # Popular penny stocks (under $5)
            'SOFI', 'NIO', 'PLUG', 'RIOT', 'MARA', 'PLTR', 'AMC', 'NOK', 'BB', 'SNDL',
            'AAL', 'CCL', 'NCLH', 'UAL', 'DAL', 'F', 'VALE', 'GOLD', 'BTG', 'HL',
            'AGNC', 'NLY', 'TWO', 'ARR', 'MFA', 'NYMT', 'IVR', 'CIM', 'MITT', 'DX',
            'ET', 'MPLX', 'EPD', 'OKE', 'WES', 'PAA', 'HESM', 'ENLC', 'DCP', 'USAC',
            'KGC', 'AUY', 'PAAS', 'AG', 'EGO', 'CDE', 'NG', 'SBSW', 'FSM', 'GORO',
            'TELL', 'GSAT', 'CLSK', 'NNDM', 'CIFR', 'BTBT', 'BITF', 'HUT', 'ARBK', 'WULF',
            'BBBY', 'GME', 'MULN', 'GNUS', 'XELA', 'BNGO', 'OCGN', 'SAVA', 'VXRT', 'NKLA',
            'RIDE', 'FSR', 'GOEV', 'WKHS', 'HYLN', 'BLNK', 'CHPT', 'EVGO', 'ARVL', 'PSNY',
            'ATER', 'BBIG', 'CEI', 'PROG', 'SDC', 'WISH', 'CLOV', 'SPCE', 'OPEN', 'RKT',
            'HOOD', 'UPST', 'DKNG', 'SKLZ', 'PTRA', 'FTCH', 'NRDY', 'TALK', 'BMBL', 'BILL'
        ]

        # Combine and deduplicate
        all_symbols = sorted(list(set(nasdaq_100 + sp500_nyse + penny_stocks)))

        print(f"Loaded {len(all_symbols)} stocks:")
        print(f"  - NASDAQ-100: {len(nasdaq_100)} stocks")
        print(f"  - S&P 500 (NYSE): {len(sp500_nyse)} stocks")
        print(f"  - Penny Stocks: {len(penny_stocks)} stocks")

        return all_symbols

    def get_5year_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """Get 5 years of daily price data from Alpaca"""
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=5*365 + 30)  # 5 years + buffer

            url = f"{self.alpaca_data}/v2/stocks/{symbol}/bars"
            params = {
                'timeframe': '1Day',
                'start': start_date.strftime('%Y-%m-%d'),
                'end': end_date.strftime('%Y-%m-%d'),
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
        symbols = self.get_nasdaq_nyse_symbols()

        print(f"Screening {len(symbols)} stocks (NASDAQ-100, S&P 500, Penny Stocks) for 30%+ drops from 5-year ATH...")

        for symbol in symbols:
            try:
                # Get price data
                df = self.get_5year_data(symbol)
                if df is None or len(df) < 100:
                    continue

                # Find 5-year ATH
                ath_5y = df['h'].max()  # highest 'high' price
                ath_date = df['h'].idxmax()
                current_price = df['c'].iloc[-1]  # latest close

                # Calculate drop percentage
                drop_pct = ((current_price - ath_5y) / ath_5y) * 100

                # Filter: Only stocks down 30% or more
                if drop_pct <= -30:
                    # Calculate price CAGR (5 years)
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
                    print(f"ALERT: {symbol}: {drop_pct:.1f}% from ATH")

            except Exception as e:
                print(f"Error processing {symbol}: {e}")
                continue

        # Sort by drop percentage (largest drops first)
        alerts.sort(key=lambda x: x.drop_pct)

        return alerts

    def create_email_html(self, alerts: List[StockAlert]) -> str:
        """Create HTML email with stock alerts"""
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; padding: 20px; }}
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
            <h2>Stock Alert: Stocks Down 30%+ from 5-Year ATH</h2>
            <p>Market Close: {datetime.now().strftime('%Y-%m-%d %H:%M ET')}</p>
            <p>Found <strong>{len(alerts)}</strong> opportunities</p>
            <p style="font-size: 14px; color: #7f8c8d;">Screened: NASDAQ-100, S&P 500, Top 100 Penny Stocks</p>

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
                    <td class="{'positive' if alert.price_cagr_5y and alert.price_cagr_5y > 0 else 'negative'}">{alert.price_cagr_5y}%</td>
                </tr>
            """

        html += """
                </tbody>
            </table>

            <p style="margin-top: 30px; color: #7f8c8d; font-size: 12px;">
                This is an automated alert from your Stock Screener<br>
                Data source: Alpaca Markets
            </p>
        </body>
        </html>
        """

        return html

    def print_console_summary(self, alerts: List[StockAlert]):
        """Print summary to console"""
        print(f"\n{'='*60}")
        print(f"SUMMARY: Found {len(alerts)} stocks down 30%+ from ATH")
        print(f"{'='*60}")
        
        for alert in alerts:
            print(f"{alert.ticker}: {alert.drop_pct}% (${alert.current_price} vs ATH ${alert.ath_5y})")

    def send_email(self, alerts: List[StockAlert]):
        """Send email alert using SendGrid API (preferred) or SMTP fallback"""
        if not self.email_configured:
            print("Email not configured - skipping email")
            return

        subject = f"Stock Alert: {len(alerts)} Stocks Down 30%+ from ATH - {datetime.now().strftime('%Y-%m-%d')}"
        html_content = self.create_email_html(alerts)

        # Try SendGrid first (works reliably on Railway)
        if self.use_sendgrid:
            try:
                print("Sending email via SendGrid API...")
                message = Mail(
                    from_email=self.email_from,
                    to_emails=self.email_to,
                    subject=subject,
                    html_content=html_content
                )
                sg = SendGridAPIClient(self.sendgrid_api_key)
                response = sg.send(message)
                print(f"Email sent successfully to {self.email_to} (SendGrid status: {response.status_code})")
                return
            except Exception as e:
                print(f"SendGrid failed: {e}")
                if not self.use_smtp:
                    print("No SMTP fallback configured. Email not sent.")
                    return

        # Fallback to SMTP if SendGrid fails or not configured
        if self.use_smtp:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.email_from
            msg['To'] = self.email_to
            msg.attach(MIMEText(html_content, 'html'))

            methods = [
                ('SMTP with STARTTLS (port 587)', 587, False),
                ('SMTP_SSL (port 465)', 465, True)
            ]

            for method_name, port, use_ssl in methods:
                try:
                    print(f"Sending email via {method_name}...")
                    if use_ssl:
                        with smtplib.SMTP_SSL('smtp.gmail.com', port, timeout=10) as server:
                            server.login(self.email_from, self.email_password)
                            server.send_message(msg)
                    else:
                        with smtplib.SMTP('smtp.gmail.com', port, timeout=10) as server:
                            server.starttls()
                            server.login(self.email_from, self.email_password)
                            server.send_message(msg)
                    print(f"Email sent successfully to {self.email_to}")
                    return
                except Exception as e:
                    print(f"{method_name} failed: {e}")

            print("All email methods failed. Email not sent.")

    def run(self):
        """Main execution"""
        print("=" * 60)
        print("Starting Stock Screener")
        print("=" * 60)

        # Screen stocks
        alerts = self.screen_stocks()

        if alerts:
            print(f"\nFound {len(alerts)} stocks down 30%+ from 5-year ATH")
            
            # Print console summary
            self.print_console_summary(alerts)

            # Send email
            self.send_email(alerts)
        else:
            print("\nNo stocks found matching criteria")

        print("\nScreener complete")


if __name__ == "__main__":
    screener = StockScreener()
    screener.run()