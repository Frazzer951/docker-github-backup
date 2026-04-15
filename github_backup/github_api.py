from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

API_ROOT = "https://api.github.com"


@dataclass(frozen=True, slots=True)
class Repo:
    name: str
    owner: str
    clone_url: str


def create_session(token: str, retries: int = 3, backoff_factor: float = 0.5) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(
        {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    )
    return session


def iter_repositories(session: requests.Session) -> Iterator[Repo]:
    yield from _iter_repo_collection(
        session,
        f"{API_ROOT}/user/repos",
        {"per_page": 100, "affiliation": "owner,collaborator,organization_member"},
    )


def iter_organization_repositories(session: requests.Session, organization: str) -> Iterator[Repo]:
    yield from _iter_repo_collection(
        session,
        f"{API_ROOT}/orgs/{organization}/repos",
        {"per_page": 100, "type": "all"},
    )


def _iter_repo_collection(session: requests.Session, url: str, params: dict[str, str | int]) -> Iterator[Repo]:
    while url:
        response = session.get(url, params=params, timeout=30)
        response.raise_for_status()

        for item in response.json():
            yield Repo(
                name=item["name"],
                owner=item["owner"]["login"],
                clone_url=item["clone_url"],
            )

        params = None
        next_link = response.links.get("next")
        url = next_link["url"] if next_link else ""
