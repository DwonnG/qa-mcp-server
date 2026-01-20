"""Tests for Jira client."""

import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

# Import directly to avoid loading all clients
from qa_mcp.clients.jira import JiraClient


class TestJiraClient:
    """Tests for JiraClient."""

    def test_init_requires_url(self) -> None:
        """Test that JIRA_URL is required."""
        with patch.dict("os.environ", {"JIRA_URL": ""}, clear=True):
            with pytest.raises(ValueError, match="JIRA_URL environment variable is required"):
                JiraClient()

    def test_init_success(self) -> None:
        """Test successful initialization."""
        with patch.dict("os.environ", {"JIRA_URL": "https://jira.example.com", "JIRA_PERSONAL_TOKEN": "token"}):
            client = JiraClient()
            assert client.base_url == "https://jira.example.com"

    @pytest.mark.asyncio
    async def test_get_issue_success(self, mock_jira_response: dict, mock_httpx_client: AsyncMock) -> None:
        """Test successful issue retrieval."""
        mock_response = MagicMock()
        mock_response.json.return_value = mock_jira_response
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.get.return_value = mock_response

        with patch.dict("os.environ", {"JIRA_URL": "https://jira.example.com", "JIRA_PERSONAL_TOKEN": "token"}):
            client = JiraClient()
            client._client = mock_httpx_client

            result = await client.get_issue("TEST-123")

            assert result["key"] == "TEST-123"
            assert result["fields"]["summary"] == "Test ticket summary"
            mock_httpx_client.get.assert_called_once_with("/issue/TEST-123")

    @pytest.mark.asyncio
    async def test_add_comment_success(self, mock_httpx_client: AsyncMock) -> None:
        """Test adding a comment to an issue."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "12345"}
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.post.return_value = mock_response

        with patch.dict("os.environ", {"JIRA_URL": "https://jira.example.com", "JIRA_PERSONAL_TOKEN": "token"}):
            client = JiraClient()
            client._client = mock_httpx_client

            result = await client.add_comment("TEST-123", "Test comment")

            assert result["status"] == "success"
            assert result["comment_id"] == "12345"
            mock_httpx_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_issues(self, mock_jira_response: dict, mock_httpx_client: AsyncMock) -> None:
        """Test searching for issues."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"issues": [mock_jira_response]}
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.post.return_value = mock_response

        with patch.dict("os.environ", {"JIRA_URL": "https://jira.example.com", "JIRA_PERSONAL_TOKEN": "token"}):
            client = JiraClient()
            client._client = mock_httpx_client

            results = await client.search_issues("project = TEST")

            assert len(results) == 1
            assert results[0]["key"] == "TEST-123"
