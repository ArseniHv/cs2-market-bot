# Multi-stage build for CS2 Market Analytics Bot
# Stage 1: Builder — installs all dependencies
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies for Prophet/cmdstanpy
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install CmdStan for Prophet
RUN python -c "import cmdstanpy; cmdstanpy.install_cmdstan()"

# Stage 2: Runtime — lean final image
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install runtime system dependencies only
RUN apt-get update && apt-get install -y \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /root/.cmdstan /root/.cmdstan

# Copy application code
COPY src/ ./src/
COPY data/ ./data/
COPY main.py .

# Create required directories
RUN mkdir -p data/cache data/alerts

# Never run as root
RUN useradd -m botuser && chown -R botuser:botuser /app
USER botuser

CMD ["python", "main.py"]