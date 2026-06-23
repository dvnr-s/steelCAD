FROM python:3.12-slim

# WeasyPrint system dependencies (Debian Bookworm/Trixie)
# Note: libgdk-pixbuf2.0-0 was renamed to libgdk-pixbuf-2.0-0 in Bookworm+
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libcairo2 \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Exclude venv if accidentally included
# .dockerignore handles this but belt-and-suspenders
RUN rm -rf venv .venv

# Expose port
EXPOSE 8000

# Run with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
