"""GitHub client for checking PRs and commits."""

import os
from typing import Any

import httpx


class GitHubClient:
    """Client for interacting with GitHub API (supports GitHub.com and Enterprise)."""

    def __init__(self) -> None:
        host = os.getenv("GITHUB_HOST", "https://api.github.com")
        if "api.github.com" in host:
            self.base_url = host
        else:
            self.base_url = f"{host}/api/v3"
        self.token = os.getenv("GITHUB_TOKEN", "")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {"Accept": "application/vnd.github+json"}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"

            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def get_commit(self, owner: str, repo: str, sha: str) -> dict[str, Any]:
        """Get commit details."""
        client = await self._get_client()
        try:
            response = await client.get(f"/repos/{owner}/{repo}/commits/{sha}")
            response.raise_for_status()
            data = response.json()
            return {
                "status": "success",
                "sha": data["sha"],
                "message": data["commit"]["message"],
                "author": data["commit"]["author"]["name"],
                "date": data["commit"]["author"]["date"],
                "url": data["html_url"],
            }
        except httpx.HTTPError as e:
            return {"status": "error", "error": str(e)}

    async def get_pr(self, owner: str, repo: str, pr_number: int) -> dict[str, Any]:
        """Get PR details."""
        client = await self._get_client()
        try:
            response = await client.get(f"/repos/{owner}/{repo}/pulls/{pr_number}")
            response.raise_for_status()
            data = response.json()
            return {
                "status": "success",
                "number": data["number"],
                "title": data["title"],
                "body": data.get("body", ""),
                "state": data["state"],
                "merged": data.get("merged", False),
                "merged_at": data.get("merged_at"),
                "merge_commit_sha": data.get("merge_commit_sha"),
                "head_sha": data["head"]["sha"],
                "head_branch": data["head"]["ref"],
                "base_branch": data["base"]["ref"],
                "url": data["html_url"],
            }
        except httpx.HTTPError as e:
            return {"status": "error", "error": str(e)}

    async def get_pr_commits(self, owner: str, repo: str, pr_number: int) -> dict[str, Any]:
        """Get commits in a PR."""
        client = await self._get_client()
        try:
            response = await client.get(f"/repos/{owner}/{repo}/pulls/{pr_number}/commits")
            response.raise_for_status()
            data = response.json()
            commits = [
                {
                    "sha": c["sha"],
                    "message": c["commit"]["message"].split("\n")[0],
                    "author": c["commit"]["author"]["name"],
                    "date": c["commit"]["author"]["date"],
                }
                for c in data
            ]
            return {"status": "success", "pr_number": pr_number, "commits": commits}
        except httpx.HTTPError as e:
            return {"status": "error", "error": str(e)}

    async def find_pr_for_commit(self, owner: str, repo: str, sha: str) -> dict[str, Any]:
        """Find the PR that introduced a commit."""
        client = await self._get_client()
        try:
            response = await client.get(
                f"/repos/{owner}/{repo}/commits/{sha}/pulls",
                headers={"Accept": "application/vnd.github+json"},
            )
            response.raise_for_status()
            data = response.json()

            if not data:
                return {"status": "success", "found": False, "message": f"No PR found for commit {sha}"}

            pr = data[0]
            return {
                "status": "success",
                "found": True,
                "pr_number": pr["number"],
                "pr_title": pr["title"],
                "pr_state": pr["state"],
                "pr_url": pr["html_url"],
            }
        except httpx.HTTPError as e:
            return {"status": "error", "error": str(e)}

    async def check_dependabot_alerts(self, owner: str, repo: str) -> dict[str, Any]:
        """Check Dependabot vulnerability alerts for a repo."""
        client = await self._get_client()
        try:
            response = await client.get(
                f"/repos/{owner}/{repo}/dependabot/alerts",
                params={"state": "open"},
            )
            response.raise_for_status()
            data = response.json()

            alerts = [
                {
                    "number": a["number"],
                    "severity": a["security_advisory"]["severity"],
                    "package": a["security_vulnerability"]["package"]["name"],
                    "summary": a["security_advisory"]["summary"],
                    "created_at": a["created_at"],
                }
                for a in data
            ]
            return {
                "status": "success",
                "repo": f"{owner}/{repo}",
                "open_alerts": len(alerts),
                "alerts": alerts,
            }
        except httpx.HTTPError as e:
            return {"status": "error", "error": str(e)}

    async def search_prs(
        self, owner: str, repo: str, search_term: str, state: str = "all"
    ) -> list[dict[str, Any]]:
        """Search for PRs mentioning a term in title or body."""
        client = await self._get_client()
        found_prs = []
        try:
            response = await client.get(
                f"/repos/{owner}/{repo}/pulls",
                params={"state": state, "per_page": 100, "sort": "updated", "direction": "desc"},
            )
            response.raise_for_status()
            data = response.json()

            search_lower = search_term.lower()
            for pr in data:
                title = (pr.get("title") or "").lower()
                body = (pr.get("body") or "").lower()

                if search_lower in title or search_lower in body:
                    found_prs.append({
                        "number": pr["number"],
                        "title": pr["title"],
                        "state": pr["state"],
                        "merged": pr.get("merged_at") is not None,
                        "merged_at": pr.get("merged_at"),
                        "html_url": pr["html_url"],
                        "user": pr["user"]["login"],
                        "created_at": pr["created_at"],
                        "updated_at": pr["updated_at"],
                    })
            return found_prs
        except httpx.HTTPError:
            return []

    async def list_recent_prs(
        self, owner: str, repo: str, state: str = "all", limit: int = 20
    ) -> dict[str, Any]:
        """List recent PRs for a repository."""
        client = await self._get_client()
        try:
            response = await client.get(
                f"/repos/{owner}/{repo}/pulls",
                params={"state": state, "per_page": limit, "sort": "updated", "direction": "desc"},
            )
            response.raise_for_status()
            data = response.json()

            prs = [
                {
                    "number": pr["number"],
                    "title": pr["title"],
                    "state": pr["state"],
                    "merged": pr.get("merged_at") is not None,
                    "merged_at": pr.get("merged_at"),
                    "user": pr["user"]["login"],
                    "updated_at": pr["updated_at"],
                }
                for pr in data
            ]
            return {"status": "success", "repo": f"{owner}/{repo}", "count": len(prs), "prs": prs}
        except httpx.HTTPError as e:
            return {"status": "error", "error": str(e)}

    async def update_pr_description(
        self, owner: str, repo: str, pr_number: int, body: str
    ) -> dict[str, Any]:
        """Update a PR's description/body."""
        client = await self._get_client()
        try:
            response = await client.patch(
                f"/repos/{owner}/{repo}/pulls/{pr_number}",
                json={"body": body},
            )
            response.raise_for_status()
            data = response.json()
            return {
                "status": "success",
                "pr_number": data["number"],
                "title": data["title"],
                "url": data["html_url"],
            }
        except httpx.HTTPError as e:
            return {"status": "error", "error": str(e)}
