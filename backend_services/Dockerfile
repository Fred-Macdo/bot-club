FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy requirements file and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Make port 8001 available to the world outside this container
EXPOSE 8001

# Define the command to run your app
CMD ["python", "src/main.py"]