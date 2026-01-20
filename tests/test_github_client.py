"""Tests for GitHub client."""

import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

# Import directly to avoid loading all clients
from qa_mcp.clients.github import GitHubClient


class TestGitHubClient:
    """Tests for GitHubClient."""

    def test_init_github_com(self) -> None:
        """Test initialization with GitHub.com."""
        with patch.dict("os.environ", {"GITHUB_HOST": "https://api.github.com", "GITHUB_TOKEN": "test"}):
            client = GitHubClient()
            assert client.base_url == "https://api.github.com"

    def test_init_enterprise(self) -> None:
        """Test initialization with GitHub Enterprise."""
        with patch.dict("os.environ", {"GITHUB_HOST": "https://github.company.com", "GITHUB_TOKEN": "test"}):
            client = GitHubClient()
            assert client.base_url == "https://github.company.com/api/v3"

    @pytest.mark.asyncio
    async def test_get_pr_success(self, mock_pr_response: dict, mock_httpx_client: AsyncMock) -> None:
        """Test successful PR retrieval."""
        mock_response = MagicMock()
        mock_response.json.return_value = mock_pr_response
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.get.return_value = mock_response

        with patch.dict("os.environ", {"GITHUB_HOST": "https://api.github.com", "GITHUB_TOKEN": "test"}):
            client = GitHubClient()
            client._client = mock_httpx_client

            result = await client.get_pr("owner", "repo", 456)

            assert result["status"] == "success"
            assert result["number"] == 456
            assert result["merged"] is True
            assert result["head_branch"] == "feature/test"

    @pytest.mark.asyncio
    async def test_get_pr_error(self, mock_httpx_client: AsyncMock) -> None:
        """Test PR retrieval with HTTP error."""
        mock_httpx_client.get.side_effect = httpx.HTTPError("Not found")

        with patch.dict("os.environ", {"GITHUB_HOST": "https://api.github.com", "GITHUB_TOKEN": "test"}):
            client = GitHubClient()
            client._client = mock_httpx_client

            result = await client.get_pr("owner", "repo", 999)

            assert result["status"] == "error"
            assert "error" in result

    @pytest.mark.asyncio
    async def test_search_prs_filters_by_term(self, mock_httpx_client: AsyncMock) -> None:
        """Test PR search filters by search term."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"number": 1, "title": "TEST-123: Fix bug", "body": "", "state": "closed", "merged_at": "2026-01-20", "html_url": "", "user": {"login": "dev"}, "created_at": "", "updated_at": ""},
            {"number": 2, "title": "Other PR", "body": "", "state": "open", "merged_at": None, "html_url": "", "user": {"login": "dev"}, "created_at": "", "updated_at": ""},
            {"number": 3, "title": "Another", "body": "Related to TEST-123", "state": "closed", "merged_at": "2026-01-19", "html_url": "", "user": {"login": "dev"}, "created_at": "", "updated_at": ""},
        ]
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.get.return_value = mock_response

        with patch.dict("os.environ", {"GITHUB_HOST": "https://api.github.com", "GITHUB_TOKEN": "test"}):
            client = GitHubClient()
            client._client = mock_httpx_client

            results = await client.search_prs("owner", "repo", "TEST-123")

            assert len(results) == 2
            assert results[0]["number"] == 1
            assert results[1]["number"] == 3
