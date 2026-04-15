# GitHub Backup

This project builds a Docker image and Python CLI for backing up every GitHub repository visible to a personal access token. Repositories are stored as bare Git repositories under `{directory}/{owner}/{repo}`.

The current implementation is aimed at unattended runs on Unraid, but the backup engine is now packaged as a normal Python module as well.

## What It Does

- Lists repositories available to the configured GitHub token.
- Optionally appends repositories from explicitly configured extra orgs.
- Optionally filters repositories by owner.
- Clones new repositories as bare repositories.
- Fetches updates for existing repositories.
- Runs on a schedule inside the container when started with `backup.sh`.

## Performance And Robustness Changes

- Uses `per_page=100` when listing repositories from the GitHub API.
- Syncs repositories concurrently with a bounded worker pool.
- Avoids rewriting the persistent config file on container startup.
- Stops embedding the token in Git remote URLs.
- Removes the expensive recursive `chown` after every run.
- Logs Git fetch ref changes when a repo actually changed.
- Suppresses per-repo no-op logs and keeps output focused on changed repos, failures, and the final summary.

## Configuration

`config.json` supports:

```json
{
  "token": "github_token_here",
  "directory": "/home/docker/backups",
  "concurrency": 4,
  "schedule_seconds": 86400,
  "failure_delay_seconds": 300,
  "extra_orgs": ["optional-extra-org"],
  "owners": ["optional-owner-filter"]
}
```

Environment variables override config values:

- `TOKEN` or `GITHUB_TOKEN`
- `BACKUP_DIRECTORY`
- `CONCURRENCY`
- `SCHEDULE`
- `FAILURE_DELAY_SECONDS`
- `EXTRA_ORGS`
- `OWNERS`

`extra_orgs` adds repositories from named organizations on top of the normal `/user/repos` sync. This is useful when your token can access an org, but you want that org included explicitly without changing the default behavior for your own repos.

## Docker

Build the image:

```bash
docker build -t github-backup:latest .
```

Run it:

```bash
docker run --rm \
  --name github-backup \
  -e TOKEN=ghp_your_token_here \
  -e SCHEDULE=86400 \
  -v "$(pwd)/config:/home/docker/github-backup/config" \
  -v "$(pwd)/backups:/home/docker/backups" \
  github-backup:latest
```

## Local Usage

```bash
python -m github_backup ./config.json
```
