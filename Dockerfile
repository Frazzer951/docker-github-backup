# Base image
FROM python:3.12-slim

# Set work directory
WORKDIR /home/docker

# Install system dependencies including git
RUN apt-get update && \
    apt-get install -y git && \
    rm -rf /var/lib/apt/lists/*

# Copy the necessary files
COPY github-backup/ ./github-backup/
COPY setup.py .
COPY config.json.example ./github-backup/
COPY backup.sh .

# Install project dependencies
RUN pip install --no-cache-dir -e .

# Set permissions
RUN chmod -R 777 /home/docker && \
    chown -R 99:100 /home/docker

# Use the non-root user to run the container
USER 99:100

# Run the script
CMD ["./backup.sh"]
