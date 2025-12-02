# Trading Bot Cloud Deployment Guide

Deploy your trading bot to run 24/7 on a cloud server.

## Quick Start (DigitalOcean - Recommended)

### 1. Create a Droplet

1. Sign up at [DigitalOcean](https://www.digitalocean.com/) (use referral link for $200 credit)
2. Create a new Droplet:
   - **Image**: Ubuntu 22.04 LTS
   - **Size**: Basic $12/month (2GB RAM, 1 CPU) - minimum recommended
   - **Region**: New York (closest to NYSE)
   - **Authentication**: SSH Key (recommended) or Password

### 2. Connect to Your Server

```bash
ssh root@your-server-ip
```

### 3. Install Docker

```bash
# Update system
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Install Docker Compose
apt install docker-compose-plugin -y

# Verify installation
docker --version
docker compose version
```

### 4. Clone Your Repository

```bash
# Install git
apt install git -y

# Clone the repo
git clone https://github.com/ariasgon/trading-bot.git
cd trading-bot
```

### 5. Configure Environment

```bash
# Create .env file
cat > .env << 'EOF'
# Alpaca API Credentials (REQUIRED)
ALPACA_API_KEY=your_api_key_here
ALPACA_SECRET_KEY=your_secret_key_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets
ALPACA_DATA_URL=https://data.alpaca.markets

# Database (uses defaults if not set)
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_secure_password_here
POSTGRES_DB=trading_bot

# Bot Settings
DEBUG=false
LOG_LEVEL=INFO
EOF

# Edit with your actual credentials
nano .env
```

### 6. Deploy

```bash
# Start all services
docker compose -f docker-compose.prod.yml up -d

# Check status
docker compose -f docker-compose.prod.yml ps

# View logs
docker compose -f docker-compose.prod.yml logs -f app
```

### 7. Access Dashboard

Open in browser: `http://your-server-ip:8000/dashboard`

---

## Automatic Bot Start on Server Reboot

The `docker-compose.prod.yml` includes:
- `restart: always` - containers restart automatically
- `bot-starter` service - auto-starts the trading bot after server is healthy

---

## Monitoring & Maintenance

### View Logs
```bash
# All logs
docker compose -f docker-compose.prod.yml logs -f

# Just the trading bot
docker compose -f docker-compose.prod.yml logs -f app

# Last 100 lines
docker compose -f docker-compose.prod.yml logs --tail=100 app
```

### Check Status
```bash
# Container status
docker compose -f docker-compose.prod.yml ps

# Bot status via API
curl http://localhost:8000/api/v1/bot/status
```

### Restart Services
```bash
# Restart everything
docker compose -f docker-compose.prod.yml restart

# Restart just the bot
docker compose -f docker-compose.prod.yml restart app
```

### Update the Bot
```bash
cd trading-bot
git pull origin main
docker compose -f docker-compose.prod.yml up -d --build
```

### Stop Everything
```bash
docker compose -f docker-compose.prod.yml down
```

---

## Security Recommendations

### 1. Set Up Firewall
```bash
# Install UFW
apt install ufw -y

# Allow SSH
ufw allow 22

# Allow trading bot dashboard
ufw allow 8000

# Enable firewall
ufw enable
```

### 2. Use HTTPS (Optional but Recommended)

Install Nginx as reverse proxy with Let's Encrypt SSL:

```bash
# Install Nginx and Certbot
apt install nginx certbot python3-certbot-nginx -y

# Configure Nginx
cat > /etc/nginx/sites-available/trading-bot << 'EOF'
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
EOF

# Enable site
ln -s /etc/nginx/sites-available/trading-bot /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx

# Get SSL certificate
certbot --nginx -d your-domain.com
```

### 3. Set Up Monitoring Alerts

Use a free uptime monitoring service:
- [UptimeRobot](https://uptimerobot.com/) - Free for 50 monitors
- [Healthchecks.io](https://healthchecks.io/) - Free cron job monitoring

Monitor: `http://your-server-ip:8000/health`

---

## Alternative: Railway (Easiest Deployment)

[Railway](https://railway.app/) provides one-click deployment:

1. Connect your GitHub repo
2. Add environment variables in Railway dashboard
3. Deploy automatically on every push

**Pros**: Zero server management, auto-scaling
**Cons**: Slightly higher cost (~$10-20/month)

---

## Alternative: AWS EC2 Free Tier

AWS offers 12 months free for t2.micro instances:

1. Create EC2 instance (t2.micro, Ubuntu 22.04)
2. Follow same steps as DigitalOcean above
3. Configure Security Group to allow port 8000

**Note**: t2.micro (1GB RAM) is minimal - may need upgrade for production.

---

## Troubleshooting

### Bot not starting
```bash
# Check logs
docker compose -f docker-compose.prod.yml logs app

# Manually start bot
curl -X POST http://localhost:8000/api/v1/bot/start
```

### Database connection errors
```bash
# Check if postgres is running
docker compose -f docker-compose.prod.yml ps db

# View database logs
docker compose -f docker-compose.prod.yml logs db
```

### Out of memory
```bash
# Check memory usage
free -h

# Upgrade your server or add swap
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

---

## Cost Comparison

| Provider | Minimum Spec | Monthly Cost | Notes |
|----------|--------------|--------------|-------|
| DigitalOcean | 2GB RAM, 1 CPU | $12 | Easy, reliable |
| Linode | 2GB RAM, 1 CPU | $10 | Good value |
| Vultr | 2GB RAM, 1 CPU | $10 | Fast deployment |
| AWS EC2 | t3.small | ~$15 | Free tier for 1 year |
| Railway | Auto-scaled | $10-20 | Easiest, no server mgmt |
| Render | 512MB RAM | $7 | May be underpowered |

**Recommended**: DigitalOcean $12/month droplet for best balance of cost/reliability.

---

## Support

- Dashboard: `http://your-server-ip:8000/dashboard`
- API Docs: `http://your-server-ip:8000/docs`
- Health Check: `http://your-server-ip:8000/health`
