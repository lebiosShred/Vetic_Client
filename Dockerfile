# Start from a standard, official Python 3.9 base image
FROM python:3.9-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install the Python dependencies defined in requirements.txt
# The --no-cache-dir flag is an extra precaution to ensure a clean install
RUN pip install --no-cache-dir -r requirements.txt

# Copy your main application file into the container
COPY main.py .

# Expose the port that Gunicorn will run on
EXPOSE 10000

# The command to run when the container starts
# This is the same command we used in Render's settings
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--timeout", "120", "main:app"]
