# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Install dumb-init for proper PID 1 signal handling
RUN apt-get update && apt-get install -y --no-install-recommends dumb-init && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# Copy the requirements file into the container at /app
COPY requirements.txt /app/requirements.txt

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# Copy the rest of the backend application code into the container at /app
COPY . /app

# Change ownership to non-root user
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Make port 8000 available to the world outside this container (if your FastAPI app runs on 8000)
EXPOSE 8000

# Define the command to run your app using Uvicorn
# If main.py is in src/, refer to it as src.main
ENTRYPOINT ["dumb-init", "--"]
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]