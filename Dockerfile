# Use an official Python runtime for ARM as a parent image
#FROM arm32v7/python:3.9-slim
FROM --platform=linux/arm64 python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container
COPY . .

# Install any needed packages specified in requirements.txt
RUN pip install --upgrade pip && \
    pip wheel --wheel-dir=/root/wheels psutil && \
    pip install --no-cache-dir --find-links=/root/wheels -r requirements.txt

RUN mkdir -p /models

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Define environment variable
ENV FLASK_APP=app.py
ENV FLASK_ENV=development

# Run app.py when the container launches
CMD ["python3", "run.py"]