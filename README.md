# CS2 Market Analytics Bot

A continuously running data pipeline and Telegram bot that tracks CS2 skin
prices, detects market anomalies, and delivers tiered alerts and ML-based
price predictions.

## Architecture
```
Skinport API (bulk, all items)
Steam Market API (historical seeding)      →   Data Collector (APScheduler, 30 min)
CSFloat API (float breakdowns)                              ↓
                                                  InfluxDB 2.x (time-series)
                                                            ↓
                                            Analytics Engine (Pandas, NumPy)
                                             ├── Liquidity Calculator
                                             ├── Inflation Detector
                                             ├── Spike Detector (tiered)
                                             ├── Trend Analyzer
                                             └── Prophet ML Predictor
                                                            ↓
                                            Alert Manager (threshold checks)
                                                            ↓
                                     Telegram Bot (commands + push alerts)
```

## Features

- Bulk price collection for all ~18,000 CS2 items every 30 minutes via Skinport
- Deep per-item analytics for tracked items stored in InfluxDB
- Market-wide spike detection via cycle-to-cycle comparison
- Tiered push alerts: 🟡 mild → 🟠 significant → 🚨 SUPERFLAG
- 7-day ML price prediction using Facebook Prophet
- Float-range price breakdown via CSFloat API
- Category-level analytics aggregation
- `/discover` command showing top movers across all CS2 items

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Database | InfluxDB 2.x |
| Scheduling | APScheduler |
| HTTP client | httpx |
| Analytics | Pandas, NumPy |
| ML prediction | Facebook Prophet |
| Bot interface | python-telegram-bot v21 |
| Containerisation | Docker, Docker Compose |
| Deployment | Oracle Cloud free tier VM (Ubuntu 22.04) |

## Data Sources

| Source | Role | Key required |
|---|---|---|
| Skinport `/v1/items` | Bulk price fetch — all items | No |
| Steam Market price history | One-time historical seeding | No |
| CSFloat `/v1/listings` | Float-range breakdown | Yes |

## Bot Commands

| Command | Description |
|---|---|
| `/price ITEM` | Current price, 24h change, trend |
| `/chart ITEM` | 30-day price history chart |
| `/track ITEM` | Add item to tracking list |
| `/untrack ITEM` | Remove item from tracking |
| `/list` | Show all tracked items |
| `/liquidity ITEM` | Liquidity score with interpretation |
| `/category CAT` | Category-level analytics |
| `/summary` | Top 5 movers across tracked items |
| `/discover` | Market-wide movers (all CS2 items) |
| `/predict ITEM` | 7-day ML price forecast with chart |
| `/float ITEM` | Float-range price breakdown |
| `/alerts on/off` | Toggle push notifications |
| `/status` | Bot status and collection info |
| `/help` | Command list |

## Alert Tiers

| Deviation | Alert |
|---|---|
| < 15% | No alert |
| 15–30% | 🟡 Mild movement |
| 30–50% | 🟠 Significant spike |
| 50%+ with volume confirmed | 🚨 SUPERFLAG: EXTREME ANOMALY |
| 50%+ with normal volume | ⚠️ Possible data anomaly |

## Analytics Methodology

**Liquidity Score:** `rolling_7d_avg(volume) / median_price`
Values above 1.0 are highly liquid, 0.5–1.0 moderate, below 0.5 illiquid.

**Inflation Detection:** Compares 7-day rolling average price to 30-day
rolling average. Deviation = `(7d_avg - 30d_avg) / 30d_avg * 100`.

**Spike Detection:** Z-score on rolling 30-day price window. Flagged if
`abs(z_score) > 2.0`.

**Trend Direction:** Linear regression slope on last 14 price points.
Classified as strong uptrend / uptrend / sideways / downtrend / strong downtrend.

## Local Development
```bash
# Clone and set up
git clone https://github.com/YOUR_USERNAME/cs2-market-bot.git
cd cs2-market-bot
python -m venv .venv
source .venv/Scripts/activate  # Windows bash
pip install -r requirements.txt

# Start InfluxDB
docker compose up influxdb -d

# Configure
cp .env.example .env
# Edit .env with your tokens

# Run tests
python tests/test_influx_connection.py
python tests/test_analytics.py
python tests/test_csfloat.py

# Single collection cycle
python main.py --collect

# Start bot
python main.py
```

## Deployment (Oracle Cloud)

See deployment steps in the repository wiki or follow Part 7 of the
build guide. Summary:
```bash
git clone https://github.com/YOUR_USERNAME/cs2-market-bot.git
cd cs2-market-bot
cp .env.example .env && nano .env
docker compose up influxdb -d && sleep 20
docker compose build bot
docker compose up -d
docker compose exec bot python main.py --seed
```

## Environment Variables

| Variable | Description |
|---|---|
| `INFLUXDB_URL` | InfluxDB connection URL |
| `INFLUXDB_TOKEN` | InfluxDB admin token |
| `INFLUXDB_ORG` | InfluxDB organisation name |
| `INFLUXDB_BUCKET` | InfluxDB bucket name |
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID |
| `CSFLOAT_API_KEY` | CSFloat API key |
| `COLLECTION_INTERVAL_MINUTES` | Price collection interval (default: 30) |
| `STEAM_REQUEST_DELAY_SECONDS` | Delay between Steam requests (default: 3) |