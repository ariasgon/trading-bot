"""
Test just the email functionality
"""
import os
from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

load_dotenv()

print("Testing Gmail SMTP...")
print()

email_from = os.getenv('EMAIL_FROM')
email_to = os.getenv('EMAIL_TO')
password = os.getenv('EMAIL_PASSWORD')

print(f"From: {email_from}")
print(f"To: {email_to}")
print(f"Password: {password[:4]}...")
print()

try:
    # Create a nice HTML test email
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Stock Screener - Test Email SUCCESS!'
    msg['From'] = email_from
    msg['To'] = email_to

    html = """
    <html>
    <body style="font-family: Arial, sans-serif; padding: 20px;">
        <h2 style="color: #27ae60;">✅ Email Test Successful!</h2>
        <p>Your Stock Screener is configured correctly and ready to send alerts!</p>
        <hr>
        <p><strong>Configuration:</strong></p>
        <ul>
            <li>From: {}</li>
            <li>To: {}</li>
            <li>SMTP: Gmail (smtp.gmail.com:465)</li>
        </ul>
        <hr>
        <p style="color: #7f8c8d; font-size: 12px;">
            This is a test message from your Stock Screener setup.
        </p>
    </body>
    </html>
    """.format(email_from, email_to)

    msg.attach(MIMEText(html, 'html'))

    print("Connecting to Gmail SMTP server...")
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        print("Logging in...")
        server.login(email_from, password)
        print("Sending email...")
        server.send_message(msg)

    print()
    print("="*60)
    print("SUCCESS! Email sent!")
    print("="*60)
    print()
    print(f"Check your inbox at: {email_to}")
    print()

except Exception as e:
    print()
    print("="*60)
    print("ERROR!")
    print("="*60)
    print(f"Error: {e}")
    print()
    print("Troubleshooting:")
    print("1. Verify App Password is correct (16 chars)")
    print("2. Remove spaces from password in .env")
    print("3. Enable 2-Step Verification")
    print("4. Create new App Password if needed")
    print()
