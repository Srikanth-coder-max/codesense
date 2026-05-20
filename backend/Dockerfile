# Use a slim, production-ready base image
FROM python:3.11-slim

# Install system dependencies (git is required for your Repo.clone_from)
# Cleanup apt lists to keep the image size small
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set up a dedicated working directory
WORKDIR /app

# Create a non-root user for security best practices
RUN useradd -m appuser

# Create a temporary directory owned by appuser to avoid permission issues
RUN mkdir -p /app/temp && chown -R appuser:appuser /app/temp

USER appuser

# Copy requirements first to leverage Docker layer caching
# This ensures pip install only re-runs if requirements.txt changes
COPY --chown=appuser:appuser requirements.txt .

# Install dependencies
# Using --no-cache-dir keeps the image size lean
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=appuser:appuser . .

# Expose port and start the application
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]