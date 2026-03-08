#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Dict, List, Optional
from xml.sax.saxutils import escape

API_URL = "https://api.github.com/graphql"
QUERY = """
query UserContributedRepositories($login: String!, $after: String) {
  user(login: $login) {
    repositoriesContributedTo(
      first: 100
      after: $after
      includeUserRepositories: true
      privacy: PUBLIC
    ) {
      totalCount
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        nameWithOwner
        stargazerCount
        url
        owner {
          login
        }
      }
    }
  }
}
""".strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update contributed repository star summary for a GitHub profile README.")
    parser.add_argument("--username", required=True, help="GitHub username to query.")
    parser.add_argument("--svg", default="assets/contributed-stars.svg", help="Output SVG path.")
    return parser.parse_args()


def graphql_request(token: str, query: str, variables: Dict[str, Optional[str]]) -> Dict:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "pppp-kaqiu-profile-readme-updater",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub GraphQL request failed with HTTP {error.code}: {body}") from error


def fetch_contributed_repositories(username: str, token: str) -> List[Dict]:
    repositories: Dict[str, Dict] = {}
    cursor: Optional[str] = None

    while True:
        data = graphql_request(token, QUERY, {"login": username, "after": cursor})
        if data.get("errors"):
            raise RuntimeError(f"GitHub GraphQL returned errors: {json.dumps(data['errors'])}")

        user = data.get("data", {}).get("user")
        if user is None:
            raise RuntimeError(f"GitHub user '{username}' was not found.")

        result = user["repositoriesContributedTo"]
        for repo in result.get("nodes", []):
            if not repo:
                continue
            repositories[repo["nameWithOwner"]] = repo

        page_info = result["pageInfo"]
        if not page_info["hasNextPage"]:
            break
        cursor = page_info["endCursor"]

    return sorted(repositories.values(), key=lambda repo: (-repo["stargazerCount"], repo["nameWithOwner"].lower()))


def render_svg(username: str, repositories: List[Dict]) -> str:
    username_lower = username.lower()
    total_repos = len(repositories)
    total_stars = sum(repo["stargazerCount"] for repo in repositories)
    external_repos = sum(1 for repo in repositories if repo["owner"]["login"].lower() != username_lower)
    top_repo = repositories[0] if repositories else None
    updated_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d UTC")

    top_repo_name = top_repo["nameWithOwner"] if top_repo else "N/A"
    top_repo_stars = top_repo["stargazerCount"] if top_repo else 0

    def metric_block(x: int, label: str, value: str) -> str:
        return (
            f'<text x="{x}" y="82" fill="#57606a" font-size="14">{escape(label)}</text>'
            f'<text x="{x}" y="124" fill="#24292f" font-size="32" font-weight="700">{escape(value)}</text>'
        )

    return f'''<svg width="495" height="195" viewBox="0 0 495 195" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc">
  <title id="title">Contributed repository stars for {escape(username)}</title>
  <desc id="desc">Auto-updated summary of stars across public repositories contributed to by {escape(username)}, including external repositories.</desc>
  <rect x="1" y="1" width="493" height="193" rx="10" fill="#ffffff" stroke="#d0d7de" />
  <text x="24" y="36" fill="#0969da" font-size="22" font-weight="700">Contributed Repo Stars</text>
  <text x="24" y="56" fill="#57606a" font-size="12">Includes public repositories you contributed to, not only owned repositories.</text>
  {metric_block(24, 'Total Stars', str(total_stars))}
  {metric_block(190, 'Public Repos', str(total_repos))}
  {metric_block(344, 'External Repos', str(external_repos))}
  <line x1="24" y1="144" x2="471" y2="144" stroke="#d8dee4" />
  <text x="24" y="168" fill="#57606a" font-size="12">Top repo</text>
  <text x="92" y="168" fill="#24292f" font-size="12" font-weight="600">{escape(top_repo_name)}</text>
  <text x="24" y="186" fill="#57606a" font-size="12">Top repo stars: {top_repo_stars} · Updated: {escape(updated_at)}</text>
</svg>
'''


def write_file(path: str, content: str) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        file.write(content)


def main() -> int:
    args = parse_args()
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("GITHUB_TOKEN is required to query contributed repositories.", file=sys.stderr)
        return 1

    repositories = fetch_contributed_repositories(args.username, token)
    svg = render_svg(args.username, repositories)
    write_file(args.svg, svg)

    total_stars = sum(repo["stargazerCount"] for repo in repositories)
    external_repos = sum(1 for repo in repositories if repo["owner"]["login"].lower() != args.username.lower())
    print(
        json.dumps(
            {
                "username": args.username,
                "total_stars": total_stars,
                "public_repos": len(repositories),
                "external_repos": external_repos,
                "svg": args.svg,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
