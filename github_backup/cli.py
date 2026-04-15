from __future__ import annotations

import argparse
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from github_backup.config import AppConfig, ConfigError, load_config
from github_backup.git_ops import MirrorResult, git_credentials_env, mirror_repo
from github_backup.github_api import Repo, create_session, iter_organization_repositories, iter_repositories

logger = logging.getLogger("github_backup")


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backup GitHub repositories as bare Git repositories")
    parser.add_argument(
        "config",
        nargs="?",
        default="config.json",
        help="Path to the JSON config file (default: %(default)s)",
    )
    parser.add_argument("--loop", action="store_true", help="Run continuously using the configured schedule")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return parser.parse_args(argv)


def _filter_repositories(repositories: list[Repo], config: AppConfig) -> list[Repo]:
    if not config.owners:
        return repositories
    return [repo for repo in repositories if repo.owner in config.owners]


def _load_repositories(config: AppConfig) -> list[Repo]:
    seen: set[tuple[str, str]] = set()
    repositories: list[Repo] = []

    with create_session(config.token) as session:
        for repo in iter_repositories(session):
            key = (repo.owner, repo.name)
            if key in seen:
                continue
            seen.add(key)
            repositories.append(repo)

        for organization in sorted(config.extra_orgs):
            logger.info("Loading repositories for extra org %s", organization)
            for repo in iter_organization_repositories(session, organization):
                key = (repo.owner, repo.name)
                if key in seen:
                    continue
                seen.add(key)
                repositories.append(repo)

    return _filter_repositories(repositories, config)


def _warn_on_legacy_nested_layout(destination: Path) -> None:
    legacy_root = destination / destination.name
    if legacy_root.exists() and legacy_root.is_dir():
        logger.warning(
            "Detected legacy nested backup layout at %s. New runs will use %s directly.",
            legacy_root,
            destination,
        )


def run_backup(config: AppConfig) -> int:
    config.directory.mkdir(parents=True, exist_ok=True)
    _warn_on_legacy_nested_layout(config.directory)

    repositories = _load_repositories(config)

    if not repositories:
        logger.info("No repositories matched the configured filters")
        return 0

    logger.info(
        "Syncing %s repositories into %s with concurrency=%s",
        len(repositories),
        config.directory,
        config.concurrency,
    )

    results: list[MirrorResult] = []
    failures = 0
    completed = 0
    changed_count = 0
    unchanged_count = 0
    total = len(repositories)

    with git_credentials_env(config.token) as git_env:
        with ThreadPoolExecutor(max_workers=config.concurrency) as executor:
            future_map = {
                executor.submit(
                    mirror_repo,
                    repo.name,
                    repo.owner,
                    repo.clone_url,
                    config.directory,
                    env=git_env,
                ): repo
                for repo in repositories
            }

            for future in as_completed(future_map):
                repo = future_map[future]
                completed += 1
                remaining = total - completed
                try:
                    result = future.result()
                except Exception as exc:  # noqa: BLE001
                    failures += 1
                    logger.error(
                        "[%s/%s, %s remaining] Failed to sync %s/%s: %s",
                        completed,
                        total,
                        remaining,
                        repo.owner,
                        repo.name,
                        exc,
                    )
                    continue

                results.append(result)
                if result.changed:
                    changed_count += 1
                    status = "new" if result.created else "updated"
                    logger.info(
                        "[%s/%s, %s remaining] Synced %s/%s (%s) in %.2fs",
                        completed,
                        total,
                        remaining,
                        result.owner,
                        result.repo,
                        status,
                        result.duration_seconds,
                    )
                    if result.details:
                        logger.info("%s", result.details)
                else:
                    unchanged_count += 1

    created_count = sum(1 for result in results if result.created)
    updated_count = sum(1 for result in results if result.changed and not result.created)
    logger.info(
        "Backup finished: %s ok, %s created, %s updated, %s unchanged, %s failed",
        len(results),
        created_count,
        updated_count,
        unchanged_count,
        failures,
    )
    return 1 if failures else 0


def run_loop(config: AppConfig) -> int:
    while True:
        started_at = time.monotonic()
        try:
            exit_code = run_backup(config)
        except Exception:  # noqa: BLE001
            logger.exception("Backup run crashed")
            exit_code = 1

        delay = config.schedule_seconds if exit_code == 0 else config.failure_delay_seconds
        elapsed = max(0, time.monotonic() - started_at)
        sleep_for = max(1, int(delay - elapsed))
        logger.info("Next run in %s seconds", sleep_for)
        time.sleep(sleep_for)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.verbose)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        logger.error("%s", exc)
        return 2

    if args.loop:
        run_loop(config)
        return 0
    return run_backup(config)
