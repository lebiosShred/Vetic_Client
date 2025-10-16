# Start from a standard, official Python 3.9 base image
FROM python:3.9-slim

# Set the working directory inside the container
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Upgrade pip and install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev && \
    pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get purge -y --auto-remove gcc python3-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Verify boxsdk installation
RUN python -c "import boxsdk; print(f'boxsdk version: {boxsdk.__version__}')"

# Copy the rest of the application
COPY . .

# Expose the port that Gunicorn will run on
EXPOSE 10000

# The command to run when the container starts
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--timeout", "120", "main:app"]
