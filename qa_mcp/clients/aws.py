"""AWS client for checking Lambda deployments and invoking APIs."""

import json as json_module
import logging
import os
from datetime import datetime
from typing import Any

import boto3
from botocore.exceptions import ClientError

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
try:
    from config import REPO_LAMBDA_MAP
except ImportError:
    REPO_LAMBDA_MAP = {}

logger = logging.getLogger(__name__)


class AWSClient:
    """Client for checking AWS Lambda deployment status and invoking APIs."""

    def __init__(self) -> None:
        self.region = os.getenv("AWS_REGION", "us-east-1")
        self._lambda_client = None
        self._apigw_client = None
        self._rest_api_cache: dict[str, str] = {}
        self._resource_cache: dict[str, dict[str, str]] = {}

    @property
    def lambda_client(self) -> Any:
        if self._lambda_client is None:
            self._lambda_client = boto3.client("lambda", region_name=self.region)
        return self._lambda_client

    @property
    def apigw_client(self) -> Any:
        if self._apigw_client is None:
            self._apigw_client = boto3.client("apigateway", region_name=self.region)
        return self._apigw_client

    def discover_rest_api(self, environment: str, api_name: str) -> str:
        """Resolve a REST API ID by environment and logical name."""
        cache_key = f"{environment}_{api_name}"
        if cache_key in self._rest_api_cache:
            return self._rest_api_cache[cache_key]

        paginator = self.apigw_client.get_paginator("get_rest_apis")
        for page in paginator.paginate():
            for item in page.get("items", []):
                if item["name"] == cache_key:
                    api_id = item["id"]
                    self._rest_api_cache[cache_key] = api_id
                    logger.info("Discovered REST API %s -> %s", cache_key, api_id)
                    return api_id

        raise ValueError(
            f"REST API '{cache_key}' not found. Check environment/api_name."
        )

    def get_resource_id(self, rest_api_id: str, path: str) -> str:
        """Map a URL path to its API Gateway resource ID."""
        if rest_api_id not in self._resource_cache:
            resources: dict[str, str] = {}
            paginator = self.apigw_client.get_paginator("get_resources")
            for page in paginator.paginate(restApiId=rest_api_id):
                for item in page.get("items", []):
                    resources[item["path"]] = item["id"]
            self._resource_cache[rest_api_id] = resources

        resource_map = self._resource_cache[rest_api_id]

        if path in resource_map:
            return resource_map[path]

        matched = self._match_path_template(path, resource_map)
        if matched:
            return resource_map[matched]

        raise ValueError(
            f"Resource path '{path}' not found in REST API {rest_api_id}. "
            f"Available paths: {sorted(resource_map.keys())}"
        )

    @staticmethod
    def _match_path_template(
        concrete_path: str, resource_map: dict[str, str]
    ) -> str | None:
        """Find the best-matching template path for a concrete URL path."""
        concrete_parts = concrete_path.strip("/").split("/")
        best_match: str | None = None
        best_literal_count = -1

        for template_path in resource_map:
            template_parts = template_path.strip("/").split("/")
            if len(template_parts) != len(concrete_parts):
                continue

            literal_count = 0
            match = True
            for t_seg, c_seg in zip(template_parts, concrete_parts):
                if t_seg.startswith("{") and t_seg.endswith("}"):
                    continue
                if t_seg != c_seg:
                    match = False
                    break
                literal_count += 1

            if match and literal_count > best_literal_count:
                best_literal_count = literal_count
                best_match = template_path

        return best_match

    def invoke_api(
        self,
        environment: str,
        api_name: str,
        http_method: str,
        path: str,
        body: str = "",
        query_string: str = "",
    ) -> dict[str, Any]:
        """Invoke an API via the API Gateway control plane."""
        rest_api_id = self.discover_rest_api(environment, api_name)
        resource_id = self.get_resource_id(rest_api_id, path)

        path_with_qs = path
        if query_string:
            path_with_qs = f"{path}?{query_string}"

        kwargs: dict[str, Any] = {
            "restApiId": rest_api_id,
            "resourceId": resource_id,
            "httpMethod": http_method.upper(),
            "pathWithQueryString": path_with_qs,
        }
        if body:
            kwargs["body"] = body

        logger.info(
            "Invoking %s %s on %s_%s (api=%s resource=%s)",
            http_method, path_with_qs, environment, api_name,
            rest_api_id, resource_id,
        )

        response = self.apigw_client.test_invoke_method(**kwargs)

        resp_body = response.get("body", "")
        try:
            parsed_body = json_module.loads(resp_body)
        except (json_module.JSONDecodeError, TypeError):
            parsed_body = resp_body

        return {
            "status_code": response.get("status"),
            "headers": response.get("headers", {}),
            "body": parsed_body,
            "log": response.get("log", ""),
        }

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
