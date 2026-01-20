"""Jenkins client for checking build status."""

import os
from typing import Any

import httpx

# Import config from package root
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
try:
    from config import JENKINS_JOBS
except ImportError:
    JENKINS_JOBS = {}


class JenkinsClient:
    """Client for checking Jenkins build status."""

    def __init__(self) -> None:
        self.base_url = os.getenv("JENKINS_URL", "")
        if not self.base_url:
            raise ValueError("JENKINS_URL environment variable is required")
        self.username = os.getenv("JENKINS_USER", "") or os.getenv("JENKINS_USERNAME", "")
        self.api_token = os.getenv("JENKINS_TOKEN", "") or os.getenv("JENKINS_API_TOKEN", "")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            auth = (self.username, self.api_token) if self.username else None
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                auth=auth,
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def get_build_info(
        self, job_path: str, build_number: int | str = "lastBuild"
    ) -> dict[str, Any]:
        """Get information about a specific build."""
        client = await self._get_client()
        url = f"/{job_path}/{build_number}/api/json"

        try:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            return {
                "status": "success",
                "build_number": data.get("number"),
                "result": data.get("result"),
                "building": data.get("building", False),
                "timestamp": data.get("timestamp"),
                "duration": data.get("duration"),
                "url": data.get("url"),
                "display_name": data.get("displayName"),
            }
        except httpx.HTTPError as e:
            return {"status": "error", "error": str(e)}

    async def get_last_successful_build(self, job_path: str) -> dict[str, Any]:
        """Get the last successful build for a job."""
        return await self.get_build_info(job_path, "lastSuccessfulBuild")

    async def check_e2e_tests(self, repo: str, commit_sha: str | None = None) -> dict[str, Any]:
        """Check E2E test status for a repository."""
        if repo not in JENKINS_JOBS:
            return {
                "status": "error",
                "error": f"Unknown repo: {repo}. Known repos: {list(JENKINS_JOBS.keys())}",
            }

        job_path = JENKINS_JOBS[repo].get("e2e")
        if not job_path:
            return {"status": "error", "error": f"No E2E job configured for {repo}"}

        build_info = await self.get_build_info(job_path)
        if build_info["status"] == "error":
            return build_info

        result = build_info["result"]
        if result == "SUCCESS":
            build_info["tests_passed"] = True
            build_info["summary"] = "E2E tests passed"
        elif result == "FAILURE":
            build_info["tests_passed"] = False
            build_info["summary"] = "E2E tests failed"
        elif result == "UNSTABLE":
            build_info["tests_passed"] = False
            build_info["summary"] = "E2E tests unstable (some failures)"
        elif build_info.get("building"):
            build_info["tests_passed"] = None
            build_info["summary"] = "E2E tests currently running"
        else:
            build_info["tests_passed"] = None
            build_info["summary"] = f"Unknown status: {result}"

        return build_info

    async def get_user_view(self, username: str, view_name: str = "Test Builds") -> dict[str, Any]:
        """Get jobs from a user's personal Jenkins view."""
        client = await self._get_client()
        view_encoded = view_name.replace(" ", "%20")
        url = f"/user/{username}/my-views/view/{view_encoded}/api/json"
        params = {"tree": "jobs[name,url,color,lastBuild[number,result,timestamp,duration]]"}

        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            jobs = []
            for job in data.get("jobs", []):
                lb = job.get("lastBuild") or {}
                color = job.get("color", "unknown")

                if "blue" in color:
                    status = "passing"
                elif "red" in color:
                    status = "failing"
                elif "anime" in color:
                    status = "running"
                elif "disabled" in color:
                    status = "disabled"
                elif "aborted" in color:
                    status = "aborted"
                else:
                    status = "unknown"

                jobs.append({
                    "name": job["name"],
                    "url": job["url"],
                    "status": status,
                    "color": color,
                    "last_build": {
                        "number": lb.get("number"),
                        "result": lb.get("result"),
                        "timestamp": lb.get("timestamp"),
                        "duration_minutes": round(lb.get("duration", 0) / 1000 / 60, 1) if lb.get("duration") else None,
                    } if lb else None,
                })

            return {"status": "success", "view_name": view_name, "job_count": len(jobs), "jobs": jobs}
        except httpx.HTTPError as e:
            return {"status": "error", "error": str(e)}

    async def trigger_build(
        self, job_path: str, parameters: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Trigger a Jenkins build with optional parameters."""
        client = await self._get_client()

        if parameters:
            url = f"/{job_path}/buildWithParameters"
            try:
                response = await client.post(url, params=parameters)
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                return {
                    "status": "error",
                    "error": f"Failed to trigger build: {e.response.status_code} - {e.response.text[:200]}",
                }
        else:
            url = f"/{job_path}/build"
            try:
                response = await client.post(url)
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                return {
                    "status": "error",
                    "error": f"Failed to trigger build: {e.response.status_code} - {e.response.text[:200]}",
                }

        queue_url = response.headers.get("Location", "")
        return {
            "status": "success",
            "message": "Build triggered successfully",
            "queue_url": queue_url,
            "job_path": job_path,
            "parameters": parameters or {},
        }

    async def trigger_e2e_test(
        self,
        repo: str,
        branch: str = "main",
        environment: str = "",
        execution_mode: str = "regression",
    ) -> dict[str, Any]:
        """Trigger E2E tests for a repo with custom branch."""
        if repo not in JENKINS_JOBS:
            return {
                "status": "error",
                "error": f"Unknown repo: {repo}. Known repos: {list(JENKINS_JOBS.keys())}",
            }

        job_path = JENKINS_JOBS[repo].get("e2e")
        if not job_path:
            return {"status": "error", "error": f"No E2E job configured for {repo}"}

        params: dict[str, str] = {
            "branch": branch,
            "environment": environment,
            "execution_mode": execution_mode,
        }

        result = await self.trigger_build(job_path, params)
        result["repo"] = repo
        result["branch"] = branch
        result["environment"] = environment
        return result

    async def get_recent_builds(self, repo: str, job_type: str = "e2e", count: int = 5) -> dict[str, Any]:
        """Get recent builds for a repository."""
        if repo not in JENKINS_JOBS:
            return {"status": "error", "error": f"Unknown repo: {repo}"}

        job_path = JENKINS_JOBS[repo].get(job_type)
        if not job_path:
            return {"status": "error", "error": f"No {job_type} job configured for {repo}"}

        client = await self._get_client()
        url = f"/{job_path}/api/json"

        try:
            response = await client.get(url, params={"tree": f"builds[number,result,timestamp,url]{{0,{count}}}"})
            response.raise_for_status()
            data = response.json()

            builds = [
                {
                    "number": build.get("number"),
                    "result": build.get("result"),
                    "timestamp": build.get("timestamp"),
                    "url": build.get("url"),
                }
                for build in data.get("builds", [])
            ]
            return {"status": "success", "repo": repo, "job_type": job_type, "builds": builds}
        except httpx.HTTPError as e:
            return {"status": "error", "error": str(e)}
