FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Environment settings
ENV PORT=8000
ENV HOST=0.0.0.0
EXPOSE 8000

# Start SalesEasy Copilot (serves both API and React UI)
CMD ["python", "run.py"]
