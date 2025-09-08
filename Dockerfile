# Multi-stage build for production-ready EmoJournal bot
FROM python:3.11-slim as builder

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.11-slim

# Create non-root user for security
RUN groupadd -r emojournal && useradd --no-log-init -r -g emojournal emojournal

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set working directory
WORKDIR /app

# Copy Python packages from builder stage
COPY --from=builder /root/.local /home/emojournal/.local

# Make sure scripts in .local are usable
ENV PATH=/home/emojournal/.local/bin:$PATH

# Copy application code
COPY app/ ./app/

# Create data directory with proper permissions
RUN mkdir -p /app/data && chown -R emojournal:emojournal /app

# Switch to non-root user
USER emojournal

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV TZ=Europe/Moscow

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:${PORT:-10000}/health', timeout=10)"

# Expose port
EXPOSE 10000

# Run the application
CMD ["python", "-m", "app.main"]
