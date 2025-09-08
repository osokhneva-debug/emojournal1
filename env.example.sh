# EmoJournal Bot Environment Variables
# Copy to .env and fill in your values

# Required: Telegram Bot Token from @BotFather
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz

# Required: Webhook URL for your Render deployment
# Replace 'your-app-name' with your actual Render service name
WEBHOOK_URL=https://your-app-name.onrender.com/webhook

# Server configuration
PORT=10000

# Timezone (IANA format)
TZ=Europe/Moscow

# Database configuration
DATABASE_URL=sqlite:///data/emojournal.db

# Optional: For PostgreSQL in production
# DATABASE_URL=postgresql://username:password@host:port/database

# Python configuration
PYTHONUNBUFFERED=1
PYTHONPATH=/app

# Optional: Logging level
LOG_LEVEL=INFO

# Optional: Development mode
# DEBUG=false