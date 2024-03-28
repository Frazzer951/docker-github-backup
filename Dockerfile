FROM alpine:3.17.2

# Prepare Alpine for use
RUN mkdir -p /home/docker/github-backup/config;
ENV HOME /home/docker

# Copy files from git
COPY github_backup /home/docker/github-backup/github_backup
COPY setup.py /home/docker/github-backup/setup.py
COPY config.json.example /home/docker/github-backup/config.json.example
COPY backup.sh /home/docker/github-backup/backup.sh

# Install prerequisites
WORKDIR /home/docker/github-backup
RUN apk add --no-cache python3 py3-pip git; \
    pip3 install --upgrade pip; \
    pip3 install -e .; \
    chmod -R 777 /home/docker; \
    chown -R 99:100 /home/docker; \
    chmod +x backup.sh;

USER 99:100
# Define default command.
CMD ["./backup.sh"]
