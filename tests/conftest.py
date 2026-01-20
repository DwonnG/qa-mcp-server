"""Pytest fixtures for QA MCP Server tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_jira_response() -> dict:
    """Sample Jira issue response."""
    return {
        "key": "TEST-123",
        "fields": {
            "summary": "Test ticket summary",
            "description": "Test description",
            "status": {"name": "Ready for QA"},
            "issuetype": {"name": "Story"},
            "priority": {"name": "Medium"},
            "assignee": {"displayName": "Test User"},
            "comment": {"comments": []},
        },
    }


@pytest.fixture
def mock_pr_response() -> dict:
    """Sample GitHub PR response."""
    return {
        "number": 456,
        "title": "TEST-123: Fix login bug",
        "state": "closed",
        "merged": True,
        "merged_at": "2026-01-20T10:00:00Z",
        "merge_commit_sha": "abc123",
        "head": {"sha": "def456", "ref": "feature/test"},
        "base": {"ref": "main"},
        "html_url": "https://github.com/org/repo/pull/456",
        "body": "Fixes TEST-123",
    }


@pytest.fixture
def mock_httpx_client() -> AsyncMock:
    """Mock httpx AsyncClient."""
    client = AsyncMock()
    client.get = AsyncMock()
    client.post = AsyncMock()
    client.put = AsyncMock()
    client.patch = AsyncMock()
    client.aclose = AsyncMock()
    return client
