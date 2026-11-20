# 🎬 Movie Ticket Alert System

Get instant notifications when ticket bookings open for your movie at your theater!

## ✨ Features

- 📱 **Multi-platform monitoring** — BookMyShow, PVR Cinemas, District (Swiggy)
- 🔔 **Triple alert channels** — Telegram, Discord, Ntfy.sh
- 🌐 **Web Dashboard** — Visual UI hosted on GitHub Pages
- ☁️ **Runs free on GitHub Actions** — checks every 5 minutes
- 🧠 **Smart dedup** — alerts you once per platform, no spam
- 🔍 **Fuzzy matching** — handles slight name variations

## 🏗️ Architecture

```
GitHub Actions (every 5 mins)
         ↓
  ┌──────────────────────┐
  │   Booking Checkers   │
  │  • BookMyShow        │
  │  • PVR Cinemas       │
  │  • District          │
  └──────────┬───────────┘
             ↓ Booking Detected!
  ┌──────────────────────┐
  │    Alert Channels    │
  │  📱 Telegram Bot     │
  │  🎮 Discord Webhook  │
  │  📡 Ntfy.sh          │
  └──────────────────────┘
```

## 🚀 Setup Guide

### Step 1: Create GitHub Repository

1. Create a new **private** repo on GitHub (e.g., `movie-alert`)
2. Push all these files to it:
   ```bash
   cd TicketAlert
   git init
   git add .
   git commit -m "Initial setup"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/movie-alert.git
   git push -u origin main
   ```

### Step 2: Set Up Alert Channels

#### 📱 Telegram Bot
1. Open Telegram, message [@BotFather](https://t.me/BotFather)
2. Send `/newbot`, follow prompts, copy the **Bot Token**
3. Message [@userinfobot](https://t.me/userinfobot) to get your **Chat ID**
4. Message your new bot (send `/start`) so it can send you messages

#### 🎮 Discord Webhook
1. Open your Discord server → **Server Settings** → **Integrations**
2. Click **Webhooks** → **New Webhook**
3. Name it "Movie Alert", choose a channel
4. Click **Copy Webhook URL**

#### 📡 Ntfy.sh
1. Install the [ntfy app](https://ntfy.sh/) on your phone
2. Subscribe to a topic name (e.g., `my-movie-alerts-123`)
3. That's it! No account needed

### Step 3: Add GitHub Secrets

Go to your repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add these secrets:

| Secret Name | Value | Required |
|---|---|---|
| `MOVIE_NAME` | Your movie name (e.g., `Pushpa 2`) | ✅ |
| `THEATER_NAME` | Theater name (e.g., `PVR Phoenix`) | ✅ |
| `CITY` | City name (e.g., `chennai`) | ✅ |
| `CITY_CODE` | BMS city code (e.g., `CHEN`) | Optional |
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather | If using Telegram |
| `TELEGRAM_CHAT_ID` | Your chat ID | If using Telegram |
| `TELEGRAM_ENABLED` | `true` | If using Telegram |
| `DISCORD_WEBHOOK_URL` | Discord webhook URL | If using Discord |
| `DISCORD_ENABLED` | `true` | If using Discord |
| `NTFY_TOPIC` | Your ntfy topic name | If using Ntfy |
| `NTFY_ENABLED` | `true` | If using Ntfy |

### Step 4: Enable GitHub Pages (for Dashboard)

1. Go to repo → **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: `main`, folder: `/ (root)`
4. Your dashboard will be at: `https://YOUR_USERNAME.github.io/movie-alert/`

### Step 5: Enable GitHub Actions

1. Go to repo → **Actions** tab
2. Click **"I understand my workflows, go ahead and enable them"**
3. The monitor will start running every 5 minutes automatically!

## 📊 BMS City Codes

| City | Code | City | Code |
|---|---|---|---|
| Mumbai | MUMBAI | Kolkata | KOLK |
| Delhi NCR | NCR | Pune | PUNE |
| Bangalore | BANG | Ahmedabad | AHMD |
| Chennai | CHEN | Kochi | KOCH |
| Hyderabad | HYD | Jaipur | JAIP |

## 🔧 Configuration

### Via Web Dashboard
Open your GitHub Pages URL and configure visually.

### Via config.json
Edit `config.json` directly:
```json
{
  "city": "chennai",
  "city_code": "CHEN",
  "movie": "Pushpa 2",
  "theater": "PVR Phoenix",
  "platforms": {
    "bms": true,
    "pvr": true,
    "district": true
  },
  "alerts": {
    "telegram": { "enabled": true, "bot_token": "...", "chat_id": "..." },
    "discord": { "enabled": true, "webhook_url": "..." },
    "ntfy": { "enabled": true, "topic": "my-alerts", "server": "https://ntfy.sh" }
  },
  "check_next_days": 7,
  "active": true
}
```

### Via Environment Variables / GitHub Secrets
All config values can be overridden with environment variables (see table above).

## 🧪 Local Testing

```bash
pip install -r requirements.txt
python monitor.py
```

## 📁 Project Structure

```
TicketAlert/
├── index.html                  # Web dashboard (GitHub Pages)
├── config.json                 # Configuration
├── state.json                  # Alert state tracking
├── monitor.py                  # Main orchestrator
├── requirements.txt            # Python dependencies
├── checkers/
│   ├── __init__.py
│   ├── bms.py                  # BookMyShow checker
│   ├── pvr.py                  # PVR Cinemas checker
│   └── district.py             # District (Swiggy) checker
├── notifiers/
│   ├── __init__.py
│   ├── telegram.py             # Telegram notifier
│   ├── discord.py              # Discord notifier
│   └── ntfy.py                 # Ntfy.sh notifier
├── .github/
│   └── workflows/
│       └── monitor.yml         # GitHub Actions workflow
└── README.md
```

## ⚠️ Important Notes

1. **GitHub Actions free tier** gives 2,000 minutes/month — checking every 5 mins uses ~8,640 mins/month. Consider checking every 10-15 mins to stay in free tier, or use a paid plan.
2. **BMS/PVR/District APIs** are internal/unofficial and may change. If a checker stops working, the error will be logged and other platforms will still be checked.
3. **State tracking** prevents duplicate alerts. Delete `state.json` contents to re-trigger alerts.

## 📄 License

MIT — Use it however you like!
