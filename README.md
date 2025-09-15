# EmoJournal Telegram Bot

🎭 **Emotion tracking bot with scientific approach and fixed scheduling**

EmoJournal helps users track emotions 4 times daily at fixed intervals (9:00, 13:00, 17:00, 21:00) and provides weekly insights based on established psychological models.

## Features

- **Fixed Scheduling**: 4 daily check-ins at predictable times: 9:00, 13:00, 17:00, 21:00
- **Scientific Approach**: Based on Russell's Circumplex, Plutchik's Wheel, NVC principles
- **Privacy-First**: Local SQLite storage, full data export, complete deletion
- **Weekly Analytics**: Emotion patterns, trigger analysis, time-based insights
- **Russian Language**: Fully localized interface and emotion vocabulary
- **Production Ready**: Webhook mode, persistent scheduling, graceful restarts
- **Works with Any Data**: Summary available from the first emotion entry

## Theoretical Foundation

The bot incorporates established emotion research:

- **Russell's Circumplex Model**: Valence × Arousal dimensional approach
- **Plutchik's Wheel of Emotions**: Basic emotions and intensity gradations  
- **NVC Feelings Inventory**: Non-judgmental emotion vocabulary
- **Affect Labeling**: Emotional regulation through verbalization
- **Cognitive Appraisal Theory**: Context-aware trigger analysis

## Quick Start (Local Development)

```bash
# Clone repository
git clone <your-repo-url>
cd emojournal-bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your bot token and settings

# Create data directory
mkdir -p data

# Run bot
python -m app.main
```

## Deployment on Render.com

### Prerequisites

1. **Telegram Bot Token**: Get from [@BotFather](https://t.me/BotFather)
2. **GitHub Repository**: Fork or create your own repo
3. **Render Account**: Sign up at [render.com](https://render.com)

### Step-by-Step Deployment

#### 1. Create Telegram Bot

```
/newbot
EmoJournal
emojournal_<your_username>_bot
```

Save the bot token (format: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`)

#### 2. Prepare Repository

Fork this repository or create new one with these files:
- All `app/` directory files  
- `requirements.txt`
- `Dockerfile`
- `render.yaml`
- `.env.example`

#### 3. Deploy on Render

1. **Connect Repository**:
   - Go to [Render Dashboard](https://dashboard.render.com)
   - Click "New" → "Web Service"
   - Connect your GitHub repository

2. **Configure Service**:
   - **Name**: `emojournal-bot` (or your choice)
   - **Environment**: Docker
   - **Region**: Choose closest to your users
   - **Branch**: `main`
   - **Build Command**: (leave default)
   - **Start Command**: (uses Dockerfile)

3. **Set Environment Variables**:
   ```
   TELEGRAM_BOT_TOKEN = your_bot_token_here
   WEBHOOK_URL = https://emojournal-bot.onrender.com/webhook
   PORT = 10000  
   TZ = Europe/Moscow
   DATABASE_URL = sqlite:///data/emojournal.db
   ```
   
   ⚠️ **Important**: Replace `emojournal-bot` in WEBHOOK_URL with your actual service name

4. **Add Persistent Disk**:
   - In service settings, add disk:
   - **Name**: `emojournal-data`
   - **Mount Path**: `/app/data`
   - **Size**: 1GB (free tier)

#### 4. Deploy and Test

1. Click "Create Web Service"
2. Wait for deployment (3-5 minutes)  
3. Check logs for "Bot started in webhook mode"
4. Test your bot: send `/start` to your bot

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Register and start emotion tracking |
| `/help` | Show help and scientific background |
| `/note` | Record emotion right now |
| `/summary` | Get weekly/monthly emotion summary (works with any amount of data) |  
| `/export` | Download your data as CSV |
| `/timezone` | Set your timezone (IANA format) |
| `/pause` | Pause daily notifications |
| `/resume` | Resume daily notifications |
| `/delete_me` | Permanently delete all your data |
| `/stats` | Show bot usage statistics |

## Architecture

```
app/
├── main.py          # Main bot logic and handlers
├── scheduler.py     # Fixed scheduling (9:00, 13:00, 17:00, 21:00)
├── db.py           # SQLAlchemy models and database access
├── i18n.py         # Russian texts and emotion categories
└── analysis.py     # Weekly insights and CSV export (works with any data)

data/
├── emojournal.db   # SQLite database
└── apscheduler.db  # APScheduler job persistence
```

## Scheduling Algorithm

Generates 4 daily fixed slots:

1. **Morning**: 09:00
2. **Afternoon**: 13:00  
3. **Evening**: 17:00
4. **Night**: 21:00

This provides predictable check-ins throughout the day while maintaining consistent 4-hour intervals.

```python
# Fixed times generated
[time(9, 0), time(13, 0), time(17, 0), time(21, 0)]
```

## Database Schema

**Users**:
- `id`, `chat_id`, `timezone`, `created_at`, `paused`, `last_activity`

**Entries**:  
- `id`, `user_id`, `ts_local`, `valence`, `arousal`, `emotions` (JSON), `cause`, `body`, `note`, `tags` (JSON)

**Schedules**:
- `id`, `user_id`, `date_local`, `times_local` (JSON), `created_at`

## Security & Privacy

- ✅ Non-root Docker container
- ✅ Input validation and rate limiting
- ✅ Local data storage only  
- ✅ Full export capability
- ✅ Complete data deletion
- ✅ No medical advice given
- ✅ No personal data in logs

## Monitoring

- Health check endpoint: `/health`
- Graceful shutdown handling
- Comprehensive error logging (no PII)
- APScheduler job persistence across restarts

## Development

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
pytest tests/ -v

# Test specific components
python -m app.db          # Database tests
python -m app.scheduler   # Scheduler algorithm test
python -m app.analysis    # Analysis tests
```

### Local Testing with Polling

For development, you can use polling mode:

```python
# In main.py, replace webhook setup with:
application.run_polling()
```

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | ✅ | - | Bot token from @BotFather |
| `WEBHOOK_URL` | ✅ | - | Your Render service URL + /webhook |
| `PORT` | ❌ | 10000 | Server port |
| `TZ` | ❌ | Europe/Moscow | Default timezone |
| `DATABASE_URL` | ❌ | sqlite:///data/emojournal.db | Database connection |

## Scaling Considerations

**Current Setup** (SQLite + single instance):
- Supports ~1,000 concurrent users
- 1GB storage ≈ 50,000 emotion entries
- Free Render tier compatible

**For Larger Scale**:
- Switch to PostgreSQL: `DATABASE_URL=postgresql://...`
- Add Redis for session storage
- Use external job scheduler (Celery)
- Enable multiple instances

## Troubleshooting

### Common Issues

**Bot doesn't respond**:
```bash
# Check logs in Render dashboard
curl https://your-app.onrender.com/health
```

**Scheduling not working**:
- Verify timezone settings
- Check APScheduler persistence
- Ensure disk storage is mounted

**Database errors**:
- Verify `/app/data` directory permissions
- Check disk space usage

### Debug Mode

```bash
# Enable detailed logging
export LOG_LEVEL=DEBUG

# Check specific components
python -c "from app.db import test_database; test_database()"
python -c "from app.scheduler import test_fixed_time_generation; test_fixed_time_generation()"
```

## Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Make changes and add tests
4. Run tests: `pytest tests/`
5. Commit: `git commit -m "Add amazing feature"`
6. Push: `git push origin feature/amazing-feature` 
7. Open Pull Request

## License

MIT License - see LICENSE file for details.

## Research References

- Russell, J. A. (1980). A circumplex model of affect. *Journal of Personality and Social Psychology*, 39(6), 1161-1178.
- Plutchik, R. (2001). The nature of emotions: Human emotions have deep evolutionary roots. *American Scientist*, 89(4), 344-350.
- Lieberman, M. D. et al. (2007). Putting feelings into words: Affect labeling disrupts amygdala activity in response to affective stimuli. *Psychological Science*, 18(5), 421-428.
- Rosenberg, M. B. (2015). *Nonviolent Communication: A Language of Life*. PuddleDancer Press.

---

**⚠️ Important**: This bot is for emotional awareness and self-reflection. It does not provide medical advice or treatment for mental health conditions. Consult qualified professionals for serious mental health concerns.
