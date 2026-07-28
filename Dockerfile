FROM python:3.12-slim

WORKDIR /app

# Install system deps (including mdbtools for .accdb conversion)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev mdbtools && \
    rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create data directories
RUN mkdir -p data/cache data/uploads logs

# Convert .accdb to SQLite at build time
RUN chmod +x convert_accdb.sh && \
    bash convert_accdb.sh \
      "نسخة البحث الدور الأول 2026 - نظام حديث.accdb" \
      "data/students.db"

# Environment
ENV PYTHONUNBUFFERED=1
ENV SOURCE_FILE=data/students.db

# Expose port for health check (Render requires a listening port)
EXPOSE 8080

# Run
CMD ["python", "-m", "bot.main"]