"""Jira API client for QA operations."""

import os
from typing import Any

import httpx

# Import config from package root
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
try:
    from config import JIRA_FIELDS, JIRA_TRANSITIONS, TEST_RESULT_VALUES
except ImportError:
    # Fallback defaults if config not present
    JIRA_FIELDS = {"validator": "customfield_XXXXX", "test_result": "customfield_XXXXX", "team": "customfield_XXXXX"}
    JIRA_TRANSITIONS = {}
    TEST_RESULT_VALUES = {}


class JiraClient:
    """Client for interacting with Jira REST API."""

    def __init__(self) -> None:
        self.base_url = os.getenv("JIRA_URL", "")
        if not self.base_url:
            raise ValueError("JIRA_URL environment variable is required")
        self.personal_token = os.getenv("JIRA_PERSONAL_TOKEN", "")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            # Set verify=False for self-signed certs (e.g., corporate Jira)
            # Set verify=True for Atlassian Cloud
            verify_ssl = os.getenv("JIRA_VERIFY_SSL", "true").lower() != "false"
            self._client = httpx.AsyncClient(
                base_url=f"{self.base_url}/rest/api/2",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.personal_token}",
                },
                timeout=30.0,
                verify=verify_ssl,
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def get_issue(self, issue_key: str) -> dict[str, Any]:
        """Get issue details."""
        client = await self._get_client()
        response = await client.get(f"/issue/{issue_key}")
        response.raise_for_status()
        return response.json()

    async def get_issue_full(self, issue_key: str) -> dict[str, Any]:
        """Get full issue details including all fields and comments."""
        client = await self._get_client()
        response = await client.get(
            f"/issue/{issue_key}",
            params={"expand": "renderedFields,changelog"},
        )
        response.raise_for_status()
        data = response.json()
        
        fields = data.get("fields", {})
        
        # Extract comments
        comments = []
        for c in fields.get("comment", {}).get("comments", []):
            comments.append({
                "id": c.get("id"),
                "author": c.get("author", {}).get("displayName", "Unknown"),
                "body": c.get("body", ""),
                "created": c.get("created"),
                "updated": c.get("updated"),
            })
        
        # Extract subtasks
        subtasks = []
        for st in fields.get("subtasks", []):
            subtasks.append({
                "key": st.get("key"),
                "summary": st.get("fields", {}).get("summary"),
                "status": st.get("fields", {}).get("status", {}).get("name"),
            })
        
        # Extract fix versions
        fix_versions = [v.get("name") for v in fields.get("fixVersions", [])]
        
        # Extract labels
        labels = fields.get("labels", [])
        
        # Extract links
        links = []
        for link in fields.get("issuelinks", []):
            link_type = link.get("type", {}).get("name", "")
            if "outwardIssue" in link:
                links.append({
                    "type": link_type,
                    "direction": "outward",
                    "key": link["outwardIssue"].get("key"),
                    "summary": link["outwardIssue"].get("fields", {}).get("summary"),
                })
            elif "inwardIssue" in link:
                links.append({
                    "type": link_type,
                    "direction": "inward",
                    "key": link["inwardIssue"].get("key"),
                    "summary": link["inwardIssue"].get("fields", {}).get("summary"),
                })
        
        return {
            "key": data.get("key"),
            "summary": fields.get("summary"),
            "description": fields.get("description"),
            "type": fields.get("issuetype", {}).get("name"),
            "status": fields.get("status", {}).get("name"),
            "priority": fields.get("priority", {}).get("name"),
            "assignee": fields.get("assignee", {}).get("displayName") if fields.get("assignee") else None,
            "reporter": fields.get("reporter", {}).get("displayName") if fields.get("reporter") else None,
            "created": fields.get("created"),
            "updated": fields.get("updated"),
            "fix_versions": fix_versions,
            "labels": labels,
            "subtasks": subtasks,
            "comments": comments,
            "links": links,
            "validator": fields.get(JIRA_FIELDS["validator"], {}).get("displayName") if fields.get(JIRA_FIELDS["validator"]) else None,
            "test_result": fields.get(JIRA_FIELDS["test_result"], {}).get("value") if fields.get(JIRA_FIELDS["test_result"]) else None,
        }

    async def search_issues(self, jql: str, max_results: int = 50) -> list[dict[str, Any]]:
        """Search for issues using JQL."""
        client = await self._get_client()
        response = await client.post(
            "/search",
            json={
                "jql": jql,
                "maxResults": max_results,
                "fields": [
                    "summary",
                    "description",
                    "status",
                    "assignee",
                    "priority",
                    "issuetype",
                    "fixVersions",
                    "comment",
                    JIRA_FIELDS["validator"],
                    JIRA_FIELDS["test_result"],
                ],
            },
        )
        response.raise_for_status()
        return response.json().get("issues", [])

    async def assign_issue(self, issue_key: str, username: str) -> dict[str, Any]:
        """Assign issue to a user."""
        client = await self._get_client()
        response = await client.put(
            f"/issue/{issue_key}/assignee",
            json={"name": username},
        )
        response.raise_for_status()
        return {"status": "success", "issue_key": issue_key, "assignee": username}

    async def set_validator(self, issue_key: str, username: str) -> dict[str, Any]:
        """Set the validator field on an issue."""
        client = await self._get_client()
        response = await client.put(
            f"/issue/{issue_key}",
            json={"fields": {JIRA_FIELDS["validator"]: {"name": username}}},
        )
        response.raise_for_status()
        return {"status": "success", "issue_key": issue_key, "validator": username}

    async def set_test_result(self, issue_key: str, result: str) -> dict[str, Any]:
        """Set the test result field (Pass, Fail, In Progress, etc.)."""
        if result.lower() not in TEST_RESULT_VALUES:
            raise ValueError(f"Invalid test result: {result}. Must be one of {list(TEST_RESULT_VALUES.keys())}")

        client = await self._get_client()
        response = await client.put(
            f"/issue/{issue_key}",
            json={"fields": {JIRA_FIELDS["test_result"]: TEST_RESULT_VALUES[result.lower()]}},
        )
        response.raise_for_status()
        return {"status": "success", "issue_key": issue_key, "test_result": result}

    async def add_comment(self, issue_key: str, comment: str) -> dict[str, Any]:
        """Add a comment to an issue."""
        client = await self._get_client()
        response = await client.post(
            f"/issue/{issue_key}/comment",
            json={"body": comment},
        )
        response.raise_for_status()
        data = response.json()
        return {
            "status": "success",
            "issue_key": issue_key,
            "comment_id": data.get("id"),
        }

    async def transition_issue(self, issue_key: str, transition_name: str) -> dict[str, Any]:
        """Transition an issue to a new status."""
        transition_id = JIRA_TRANSITIONS.get(transition_name.lower())
        if not transition_id:
            raise ValueError(
                f"Unknown transition: {transition_name}. "
                f"Must be one of {list(JIRA_TRANSITIONS.keys())}"
            )

        client = await self._get_client()
        response = await client.post(
            f"/issue/{issue_key}/transitions",
            json={"transition": {"id": transition_id}},
        )
        response.raise_for_status()
        return {
            "status": "success",
            "issue_key": issue_key,
            "transition": transition_name,
        }

    async def claim_for_qa(self, issue_key: str, username: str) -> dict[str, Any]:
        """Claim a ticket for QA validation (assign + set validator + set in progress)."""
        results = {
            "issue_key": issue_key,
            "username": username,
            "operations": [],
        }

        await self.assign_issue(issue_key, username)
        results["operations"].append("assigned")

        await self.set_validator(issue_key, username)
        results["operations"].append("validator_set")

        await self.set_test_result(issue_key, "in_progress")
        results["operations"].append("test_result_in_progress")

        results["status"] = "success"
        return results

    async def resolve_pass(self, issue_key: str, comment: str) -> dict[str, Any]:
        """Resolve a ticket as passed (add comment + transition + set pass)."""
        results = {
            "issue_key": issue_key,
            "operations": [],
        }

        await self.add_comment(issue_key, comment)
        results["operations"].append("comment_added")

        await self.transition_issue(issue_key, "resolved")
        results["operations"].append("transitioned_to_resolved")

        await self.set_test_result(issue_key, "pass")
        results["operations"].append("test_result_pass")

        results["status"] = "success"
        return results

    async def fail_and_reopen(self, issue_key: str, comment: str) -> dict[str, Any]:
        """Fail a ticket and reopen it (add comment + transition + set fail)."""
        results = {
            "issue_key": issue_key,
            "operations": [],
        }

        await self.add_comment(issue_key, comment)
        results["operations"].append("comment_added")

        await self.transition_issue(issue_key, "reopened")
        results["operations"].append("transitioned_to_reopened")

        await self.set_test_result(issue_key, "fail")
        results["operations"].append("test_result_fail")

        results["status"] = "success"
        return results

    async def create_issue(
        self,
        project: str,
        issue_type: str,
        summary: str,
        description: str = "",
        epic_link: str | None = None,
        fix_version: str | None = None,
    ) -> dict[str, Any] | None:
        """Create a new Jira issue."""
        client = await self._get_client()

        fields = {
            "project": {"key": project},
            "issuetype": {"name": issue_type},
            "summary": summary,
            "description": description,
        }

        if epic_link:
            fields["customfield_12340"] = epic_link

        if fix_version:
            fields["fixVersions"] = [{"name": fix_version}]

        try:
            response = await client.post("/issue", json={"fields": fields})
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error creating issue: {e}")
            return None

    async def create_subtask(
        self,
        parent_key: str,
        summary: str,
        description: str = "",
    ) -> dict[str, Any] | None:
        """Create a subtask under a parent issue."""
        client = await self._get_client()

        parent = await self.get_issue(parent_key)
        project_key = parent["fields"]["project"]["key"]

        fields = {
            "project": {"key": project_key},
            "parent": {"key": parent_key},
            "issuetype": {"name": "Sub-task"},
            "summary": summary,
            "description": description,
        }

        try:
            response = await client.post("/issue", json={"fields": fields})
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error creating subtask: {e}")
            return None

    async def get_subtasks(self, parent_key: str) -> list[dict[str, Any]]:
        """Get all subtasks for a parent issue."""
        jql = f'parent = {parent_key} ORDER BY key ASC'
        return await self.search_issues(jql, max_results=100)

    async def update_issue(
        self,
        issue_key: str,
        summary: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Update an issue's summary and/or description."""
        client = await self._get_client()

        fields: dict[str, Any] = {}
        if summary is not None:
            fields["summary"] = summary
        if description is not None:
            fields["description"] = description

        if not fields:
            return {"status": "error", "error": "No fields to update"}

        response = await client.put(
            f"/issue/{issue_key}",
            json={"fields": fields},
        )
        response.raise_for_status()
        return {
            "status": "success",
            "issue_key": issue_key,
            "updated_fields": list(fields.keys()),
        }
