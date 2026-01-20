"""AWS client for checking Lambda deployments."""

import os
from datetime import datetime
from typing import Any

import boto3
from botocore.exceptions import ClientError

# Import config from package root
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
try:
    from config import REPO_LAMBDA_MAP
except ImportError:
    REPO_LAMBDA_MAP = {}


class AWSClient:
    """Client for checking AWS Lambda deployment status."""

    def __init__(self) -> None:
        self.region = os.getenv("AWS_REGION", "us-east-1")
        self._lambda_client = None

    @property
    def lambda_client(self) -> Any:
        if self._lambda_client is None:
            self._lambda_client = boto3.client("lambda", region_name=self.region)
        return self._lambda_client

    def get_lambda_last_modified(self, function_name: str) -> dict[str, Any]:
        """Get the LastModified timestamp of a Lambda function."""
        try:
            response = self.lambda_client.get_function(FunctionName=function_name)
            last_modified = response["Configuration"]["LastModified"]
            return {
                "function_name": function_name,
                "last_modified": last_modified,
                "status": "success",
            }
        except ClientError as e:
            return {
                "function_name": function_name,
                "error": str(e),
                "status": "error",
            }

    def check_deployment(
        self,
        repo: str,
        environment: str,
        commit_timestamp: datetime | None = None,
    ) -> dict[str, Any]:
        """Check if a repo's Lambda functions are deployed in the specified environment."""
        if repo not in REPO_LAMBDA_MAP:
            return {
                "status": "error",
                "error": f"Unknown repo: {repo}. Known repos: {list(REPO_LAMBDA_MAP.keys())}",
            }

        if environment not in REPO_LAMBDA_MAP[repo]:
            return {
                "status": "error",
                "error": f"Unknown environment: {environment} for repo {repo}",
            }

        functions = REPO_LAMBDA_MAP[repo][environment]
        results = []

        for func_name in functions:
            func_result = self.get_lambda_last_modified(func_name)
            if func_result["status"] == "success" and commit_timestamp:
                lambda_time = datetime.fromisoformat(
                    func_result["last_modified"].replace("Z", "+00:00")
                )
                func_result["deployed_after_commit"] = lambda_time > commit_timestamp
            results.append(func_result)

        all_deployed = all(
            r.get("deployed_after_commit", r.get("status") == "success")
            for r in results
        )

        return {
            "status": "success",
            "repo": repo,
            "environment": environment,
            "all_deployed": all_deployed,
            "functions": results,
        }

    def get_deployment_summary(self, repo: str, environment: str) -> str:
        """Get a human-readable deployment summary."""
        result = self.check_deployment(repo, environment)

        if result["status"] == "error":
            return f"Error: {result['error']}"

        lines = [f"Deployment status for {repo} in {environment}:"]
        for func in result["functions"]:
            if func["status"] == "success":
                lines.append(f"  [OK] {func['function_name']}: {func['last_modified']}")
            else:
                lines.append(f"  [ERROR] {func['function_name']}: {func.get('error', 'Unknown error')}")

        return "\n".join(lines)
