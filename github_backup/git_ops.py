from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import textwrap
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

FETCH_REFSPEC = "+refs/heads/*:refs/heads/*"


@dataclass(frozen=True, slots=True)
class MirrorResult:
    repo: str
    owner: str
    created: bool
    changed: bool
    duration_seconds: float
    details: str = ""


def _run_git(args: list[str], *, cwd: Path, env: dict[str, str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return _normalize_git_output(result.stdout, result.stderr)


def _normalize_git_output(stdout: str, stderr: str) -> str:
    lines = [line.rstrip() for line in f"{stdout}\n{stderr}".splitlines() if line.strip()]
    return "\n".join(lines)


@contextmanager
def git_credentials_env(token: str) -> Iterator[dict[str, str]]:
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False, encoding="utf-8") as handle:
        handle.write(
            textwrap.dedent(
                """\
                #!/bin/sh
                case "$1" in
                    *Username*) printf '%s\n' "$GITHUB_BACKUP_GIT_USERNAME" ;;
                    *Password*) printf '%s\n' "$GITHUB_BACKUP_GIT_PASSWORD" ;;
                    *) exit 1 ;;
                esac
                """
            )
        )
        helper_path = Path(handle.name)

    helper_path.chmod(helper_path.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env.update(
        {
            "GIT_ASKPASS": str(helper_path),
            "GIT_TERMINAL_PROMPT": "0",
            "GITHUB_BACKUP_GIT_USERNAME": "x-access-token",
            "GITHUB_BACKUP_GIT_PASSWORD": token,
        }
    )

    try:
        yield env
    finally:
        helper_path.unlink(missing_ok=True)


def mirror_repo(repo_name: str, owner: str, clone_url: str, destination: Path, *, env: dict[str, str]) -> MirrorResult:
    owner_path = destination / owner
    owner_path.mkdir(parents=True, exist_ok=True)
    repo_path = owner_path / repo_name

    created = not (repo_path / "config").exists()
    started = monotonic()

    if created:
        _run_git(["clone", "--bare", "--origin", "origin", clone_url, repo_name], cwd=owner_path, env=env)
        changed = True
        details = ""
    else:
        _run_git(["remote", "set-url", "origin", clone_url], cwd=repo_path, env=env)
        details = _run_git(
            ["fetch", "--force", "--prune", "--tags", "origin", FETCH_REFSPEC],
            cwd=repo_path,
            env=env,
        )
        changed = bool(details)

    return MirrorResult(
        repo=repo_name,
        owner=owner,
        created=created,
        changed=changed,
        duration_seconds=monotonic() - started,
        details=details,
    )
