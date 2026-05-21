# Use a slim, production-ready base image
FROM python:3.11-slim

# Install system dependencies (git is required for Repo.clone_from)
# Cleanup apt lists to keep the image size small
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set up a dedicated working directory
WORKDIR /app

# Create a non-root user for security best practices
RUN useradd -m appuser

# Copy requirements first (as root, before switching user) to leverage layer caching
COPY requirements.txt .

# Install dependencies as root so pip can write to site-packages without issues
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

# Copy all application code
COPY . .

# --- CRITICAL FIX ---
# Create writeable directories AND set ownership AFTER all COPY commands.
# If done before COPY, the COPY layer can silently overwrite directory ownership.
# /app/temp  -> safe scratch space for temporary files (replaces /tmp)
# /app/repos -> persistent git repository caching
# /app/chromadb -> persistent vector DB storage
RUN mkdir -p /app/temp /app/repos /app/chromadb \
    && chown -R appuser:appuser /app

# Set TMPDIR so that tempfile.gettempdir() and any C-level library
# that reads $TMPDIR also use our writeable directory, not the root-owned /tmp.
ENV TMPDIR=/app/temp

# Configure git to trust the /app directory (avoids 'dubious ownership' warnings
# when the cloned repo is owned by appuser but git sees a different uid).
RUN git config --global --add safe.directory '*'

# Switch to non-root user for runtime
USER appuser

# Expose port and start the application
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]