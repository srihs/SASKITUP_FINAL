# Dockerfile for Django SASKITUP Application
# Optimized for production with external database

FROM python:3.13-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # MySQL client libraries for PyMySQL
    default-libmysqlclient-dev \
    # Build essentials for compiling Python packages
    gcc \
    g++ \
    # Required for Pillow (image processing)
    libjpeg-dev \
    libpng-dev \
    zlib1g-dev \
    # Required for cryptography package
    libffi-dev \
    libssl-dev \
    # Required for PDF generation (xhtml2pdf and reportlab)
    libxml2-dev \
    libxslt1-dev \
    # Required for reportlab (FreeType for font rendering)
    libfreetype6-dev \
    liblcms2-dev \
    # Required for WeasyPrint
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    shared-mime-info \
    # Utilities
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create application directory
WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install gunicorn

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/media /app/staticfiles /app/temp_uploads /app/logs

# Collect static files
RUN python manage.py collectstatic --noinput || true

# Create non-root user for security
RUN useradd -m -u 1000 djangouser && \
    chown -R djangouser:djangouser /app

# Switch to non-root user
USER djangouser

# Expose port 8000
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Default command: run Gunicorn server
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "kitup.wsgi:application"]
