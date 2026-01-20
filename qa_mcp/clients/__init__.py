"""Service client integrations for QA MCP Server.

Clients are imported lazily to avoid requiring all dependencies.
Import specific clients directly: `from qa_mcp.clients.jira import JiraClient`
"""

__all__ = [
    "JiraClient",
    "GitHubClient",
    "JenkinsClient",
    "AWSClient",
    "WebexClient",
    "AIClient",
    "SecretManager",
]


def __getattr__(name: str):
    """Lazy import clients to avoid requiring all dependencies."""
    if name == "JiraClient":
        from .jira import JiraClient
        return JiraClient
    elif name == "GitHubClient":
        from .github import GitHubClient
        return GitHubClient
    elif name == "JenkinsClient":
        from .jenkins import JenkinsClient
        return JenkinsClient
    elif name == "AWSClient":
        from .aws import AWSClient
        return AWSClient
    elif name == "WebexClient":
        from .webex import WebexClient
        return WebexClient
    elif name == "AIClient":
        from .ai import AIClient
        return AIClient
    elif name == "SecretManager":
        from .ai import SecretManager
        return SecretManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
