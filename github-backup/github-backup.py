import argparse
import errno
import json
import os
import re
import subprocess
import sys
import time
from typing import Dict, Iterator, Tuple, Union
from urllib.parse import urlparse, urlunparse

import requests


def get_json(url: str, session: requests.Session) -> Iterator[Dict]:
    """
    Fetch JSON data from a URL using pagination, authentication, and handling rate limits.

    Args:
        url (str): The base URL to fetch data from.
        session (requests.Session): The requests session for making HTTP requests.
        token (str): The GitHub personal access token for authentication.

    Yields:
        dict: The JSON data from each page of the response.
    """
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
    """
    Check if a name is valid according to a regular expression pattern.

    Args:
        name (str): The name to be checked.

    Raises:
        ValueError: If the name is invalid.

    Returns:
        str: The validated name.
    """
    pattern = r"^\w[-\.\w]*$"
    if not re.match(pattern, name):
        raise ValueError(f"Invalid name '{name}'")
    return name


def mkdir(path: str) -> bool:
    """
    Create a directory if it doesn't exist.

    Args:
        path (str): The path to the directory.

    Returns:
        bool: True if a new directory was created, False otherwise.
    """
    try:
        os.makedirs(path, mode=0o770)
        return True
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
        return False


def prepare_repo_url(repo_url: str, username: str, token: str) -> str:
    """
    Prepare the repository URL for cloning with authentication.

    Args:
        repo_url (str): The original repository URL.
        username (str): The GitHub username.
        token (str): The GitHub personal access token.

    Returns:
        str: The prepared repository URL with authentication credentials.
    """
    parsed = urlparse(repo_url)
    modified = list(parsed)
    modified[1] = f"{username}:{token}@{parsed.netloc}"
    return urlunparse(modified)


def init_bare_repo(repo_path: str) -> None:
    """
    Initialize a bare Git repository at the given path.

    Args:
        repo_path (str): The path to the repository.
    """
    subprocess.run(["git", "init", "--bare", "--quiet"], cwd=repo_path, check=True)


def fetch_repo(repo_path: str, repo_url: str) -> None:
    """
    Fetch the remote repository into the bare repository.

    Args:
        repo_path (str): The path to the bare repository.
        repo_url (str): The URL of the remote repository.
    """
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


def mirror(repo_name: str, repo_url: str, to_path: str, username: str, token: str) -> Tuple[str, str]:
    """
    Mirror a GitHub repository to a local directory.

    Args:
        repo_name (str): The name of the repository.
        repo_url (str): The URL of the remote repository.
        to_path (str): The path to the directory where the repository will be mirrored.
        username (str): The GitHub username.
        token (str): The GitHub personal access token.

    Returns:
        Tuple[str, str]: The owner and name of the mirrored repository.
    """
    repo_path = os.path.join(to_path, repo_name)
    os.makedirs(repo_path, exist_ok=True)

    init_bare_repo(repo_path)

    authenticated_repo_url = prepare_repo_url(repo_url, username, token)
    fetch_repo(repo_path, authenticated_repo_url)

    return repo_name, repo_url.split("/")[-2]


def main():
    parser = argparse.ArgumentParser(description="Backup GitHub repositories")
    parser.add_argument("config", metavar="CONFIG", help="a configuration file")
    args = parser.parse_args()

    with open(args.config, "rb") as f:
        config = json.loads(f.read())

    owners: Union[list[str], None] = config.get("owners")
    token: str = config["token"]
    path: str = os.path.expanduser(config["directory"])
    if mkdir(path):
        print(f"Created directory {path}", file=sys.stderr)

    with requests.Session() as session:
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
