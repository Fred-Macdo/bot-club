# Use an official Python runtime as a parent image
FROM python:3.13-slim

# Install system dependencies for TA-Lib
RUN apt-get update && apt-get install -y \
    build-essential \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install TA-Lib C library
RUN wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
    tar -xzf ta-lib-0.4.0-src.tar.gz && \
    cd ta-lib/ && \
    ./configure --prefix=/usr && \
    make && \
    make install && \
    cd .. && \
    rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt /app/requirements.txt

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# Copy the rest of the backend application code into the container at /app
COPY . /app

# Make port 8000 available to the world outside this container (if your FastAPI app runs on 8000)
EXPOSE 8000

# Define the command to run your app using Uvicorn
# If main.py is in src/, refer to it as src.main
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]