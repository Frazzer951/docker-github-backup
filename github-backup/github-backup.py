import argparse
import errno
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Iterator
from urllib.parse import urlparse, urlunparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def get_json(url: str, session: requests.Session) -> Iterator[dict]:
    while True:
        try:
            response = session.get(url, timeout=10)
            response.raise_for_status()

            yield response.json()

            if "next" not in response.links:
                break
            url = response.links["next"]["url"]

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code
            if (
                status_code == 403
                and "X-RateLimit-Remaining" in e.response.headers
                and e.response.headers["X-RateLimit-Remaining"] == "0"
            ):
                reset_time = int(e.response.headers["X-RateLimit-Reset"])
                wait_seconds = reset_time - int(time.time()) + 10  # Adding a buffer
                print(f"Rate limit exceeded. Waiting for {wait_seconds} seconds.", file=sys.stderr)
                time.sleep(wait_seconds)
                continue
            elif 400 <= status_code < 500:
                print(f"Client error: {e}", file=sys.stderr)
                break
            else:
                print(f"Server error: {e}", file=sys.stderr)
                time.sleep(5)  # Wait a bit before retrying
                continue
        except requests.exceptions.RequestException as e:
            print(f"Error fetching data from {url}: {e}", file=sys.stderr)
            break


def check_name(name: str) -> str:
    pattern = r"^\w[-\.\w]*$"
    if not re.match(pattern, name):
        raise ValueError(f"Invalid name '{name}'")
    return name


def mkdir(path: str) -> bool:
    try:
        os.makedirs(path, mode=0o770)
        return True
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
        return False


def prepare_repo_url(repo_url: str, username: str, token: str) -> str:
    parsed = urlparse(repo_url)
    modified = list(parsed)
    modified[1] = f"{username}:{token}@{parsed.netloc}"
    return urlunparse(modified)


def init_bare_repo(repo_path: str) -> None:
    subprocess.run(["git", "init", "--bare", "--quiet"], cwd=repo_path, check=True)


def fetch_repo(repo_path: str, repo_url: str) -> None:
    subprocess.run(
        [
            "git",
            "fetch",
            "--force",
            "--prune",
            "--tags",
            repo_url,
            "refs/heads/*:refs/heads/*",
        ],
        cwd=repo_path,
        check=True,
    )


def mirror(repo_name: str, repo_url: str, to_path: str, username: str, token: str) -> tuple[str, str]:
    repo_path = os.path.join(to_path, repo_name)
    os.makedirs(repo_path, exist_ok=True)

    init_bare_repo(repo_path)

    authenticated_repo_url = prepare_repo_url(repo_url, username, token)
    fetch_repo(repo_path, authenticated_repo_url)

    return repo_name, repo_url.split("/")[-2]


def create_session(retries: int = 3, backoff_factor: float = 0.3) -> requests.Session:
    session = requests.Session()
    retry = Retry(total=retries, backoff_factor=backoff_factor, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def main():
    parser = argparse.ArgumentParser(description="Backup GitHub repositories")
    parser.add_argument("config", metavar="CONFIG", help="a configuration file")
    args = parser.parse_args()

    with open(args.config) as f:
        config = json.load(f)

    owners: list[str] | None = config.get("owners")
    token: str = config["token"]
    path: str = os.path.expanduser(config["directory"])
    if mkdir(path):
        print(f"Created directory {path}", file=sys.stderr)

    with create_session() as session:
        session.headers.update({"Authorization": f"token {token}"})
        user: dict = next(get_json("https://api.github.com/user", session))
        for page in get_json("https://api.github.com/user/repos", session):
            for repo in page:
                name: str = check_name(repo["name"])
                owner: str = check_name(repo["owner"]["login"])
                clone_url: str = repo["clone_url"]

                if owners and owner not in owners:
                    continue

                owner_path: str = os.path.join(path, owner)
                os.makedirs(owner_path, exist_ok=True)
                mirror(name, clone_url, owner_path, user["login"], token)


if __name__ == "__main__":
    main()
