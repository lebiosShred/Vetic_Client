# Start from a standard, official Python 3.9 base image
FROM python:3.9-slim

# Set the working directory inside the container
WORKDIR /app

# --- DEBUGGING STEP ---
# Copy everything from the repository root into the container's current directory
COPY . .
# Now, list the files to verify they were copied correctly.
# The output of this command will appear in your Render build logs.
RUN ls -la
# --- END DEBUGGING STEP ---

# Install the Python dependencies from the (now verified) requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port that Gunicorn will run on
EXPOSE 10000

# The command to run when the container starts
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--timeout", "120", "main:app"]
