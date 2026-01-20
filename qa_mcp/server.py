#!/usr/bin/env python3
"""QA MCP Server - Automate QA workflows for development teams."""

import logging
import os
import sys
from typing import Any

from dotenv import load_dotenv
from fastmcp import FastMCP

# Add parent directory to path for config import
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from qa_mcp.clients import AWSClient, GitHubClient, JenkinsClient, JiraClient, WebexClient

# Try to import config - use defaults if not present
try:
    from config import JQL_TEMPLATES, QA_COMMENT_TEMPLATES
except ImportError:
    JQL_TEMPLATES = {
        "ready_for_qa": "project = {project} AND status = 'Ready for QA' ORDER BY priority DESC",
        "in_progress": "project = {project} AND status = 'In Progress' ORDER BY updated DESC",
    }
    QA_COMMENT_TEMPLATES = {
        "pass": "h3. QA Validation - PASS\n\n*Environment:* {environment}\n\n*Verification:*\n{verification_steps}\n\n*Test Result:* PASS - {summary}",
        "pass_vulnerability": "h3. QA Validation - PASS\n\n*Environment:* {environment}\n\nVerified via PR #{pr_number}",
        "fail": "h3. QA Validation - FAIL\n\n*Environment:* {environment}\n\n*Issue:* {issue_description}\n\n*Steps:*\n{steps}\n\n*Expected:* {expected}\n*Actual:* {actual}",
    }

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize MCP server
mcp = FastMCP("qa-automation")

# Initialize clients (lazy initialization)
_jira: JiraClient | None = None
_aws: AWSClient | None = None
_jenkins: JenkinsClient | None = None
_github: GitHubClient | None = None
_webex: WebexClient | None = None
_ai_client: Any = None
_secret_manager: Any = None

# Handler instances (lazy initialization)
_handlers: dict | None = None


def get_jira() -> JiraClient:
    global _jira
    if _jira is None:
        _jira = JiraClient()
    return _jira


def get_aws() -> AWSClient:
    global _aws
    if _aws is None:
        _aws = AWSClient()
    return _aws


def get_jenkins() -> JenkinsClient:
    global _jenkins
    if _jenkins is None:
        _jenkins = JenkinsClient()
    return _jenkins


def get_github() -> GitHubClient:
    global _github
    if _github is None:
        _github = GitHubClient()
    return _github


def get_webex() -> WebexClient:
    global _webex
    if _webex is None:
        _webex = WebexClient()
    return _webex


def get_ai_client() -> Any:
    """Get AI client (requires AWS credentials)."""
    global _ai_client, _secret_manager
    if _ai_client is None:
        try:
            from qa_mcp.clients import AIClient, SecretManager
            _secret_manager = SecretManager()
            _ai_client = AIClient(_secret_manager)
            logger.info("AI client initialized successfully")
        except Exception as e:
            logger.warning(f"Could not initialize AI client: {e}")
            _ai_client = None
    return _ai_client


def get_handlers() -> dict | None:
    """Initialize all AI-powered handlers."""
    global _handlers
    if _handlers is not None:
        return _handlers

    ai_client = get_ai_client()
    if ai_client is None:
        return None

    try:
        from qa_mcp.handlers import (
            CommentSummaryHandler,
            EpicAnalysisHandler,
            ReproductionStepsHandler,
            RootCauseHandler,
            StoryAnalysisHandler,
            TestCasesHandler,
        )

        jira = get_jira()
        _handlers = {
            "comment_summary": CommentSummaryHandler(ai_client, jira),
            "test_cases": TestCasesHandler(ai_client),
            "root_cause": RootCauseHandler(ai_client),
            "reproduction_steps": ReproductionStepsHandler(ai_client),
            "story_analysis": StoryAnalysisHandler(ai_client, jira),
            "epic_analysis": EpicAnalysisHandler(ai_client, jira),
        }
        return _handlers
    except Exception as e:
        logger.error(f"Failed to initialize handlers: {e}")
        return None


# ============================================================================
# JIRA TOOLS
# ============================================================================


@mcp.tool()
async def qa_find_ready_tickets(
    project: str,
    team: str = "",
    max_results: int = 20,
) -> dict[str, Any]:
    """Find Jira tickets waiting in the QA queue ready to be tested."""
    jql = JQL_TEMPLATES["ready_for_qa"].format(project=project, team=team)
    jira = get_jira()
    issues = await jira.search_issues(jql, max_results)

    tickets = [
        {
            "key": issue["key"],
            "summary": issue["fields"]["summary"],
            "type": issue["fields"]["issuetype"]["name"],
            "priority": issue["fields"]["priority"]["name"],
            "status": issue["fields"]["status"]["name"],
        }
        for issue in issues
    ]

    return {"status": "success", "count": len(tickets), "jql": jql, "tickets": tickets}


@mcp.tool()
async def qa_find_in_progress(
    project: str,
    team: str = "",
    max_results: int = 20,
) -> dict[str, Any]:
    """Find tickets developers are currently working on."""
    jql = JQL_TEMPLATES["in_progress"].format(project=project, team=team)
    jira = get_jira()
    issues = await jira.search_issues(jql, max_results)

    tickets = [
        {
            "key": issue["key"],
            "summary": issue["fields"]["summary"],
            "type": issue["fields"]["issuetype"]["name"],
            "status": issue["fields"]["status"]["name"],
            "assignee": issue["fields"].get("assignee", {}).get("displayName", "Unassigned") if issue["fields"].get("assignee") else "Unassigned",
        }
        for issue in issues
    ]

    return {"status": "success", "count": len(tickets), "tickets": tickets}


@mcp.tool()
async def qa_claim_ticket(issue_key: str, username: str) -> dict[str, Any]:
    """Assign yourself as the QA validator on a ticket."""
    jira = get_jira()
    return await jira.claim_for_qa(issue_key, username)


@mcp.tool()
async def qa_resolve_pass(
    issue_key: str,
    environment: str,
    verification_summary: str,
    verification_steps: list[str],
) -> dict[str, Any]:
    """Mark a ticket as QA PASSED and close it."""
    steps_formatted = "\n".join(f"- {step}" for step in verification_steps)
    comment = QA_COMMENT_TEMPLATES["pass"].format(
        environment=environment,
        verification_steps=steps_formatted,
        summary=verification_summary,
    )
    jira = get_jira()
    return await jira.resolve_pass(issue_key, comment)


@mcp.tool()
async def qa_fail_ticket(
    issue_key: str,
    environment: str,
    issue_description: str,
    steps_to_reproduce: list[str],
    expected: str,
    actual: str,
) -> dict[str, Any]:
    """Mark a ticket as QA FAILED and reopen it for dev."""
    steps_formatted = "\n".join(f"{i+1}. {step}" for i, step in enumerate(steps_to_reproduce))
    comment = QA_COMMENT_TEMPLATES["fail"].format(
        environment=environment,
        issue_description=issue_description,
        steps=steps_formatted,
        expected=expected,
        actual=actual,
    )
    jira = get_jira()
    return await jira.fail_and_reopen(issue_key, comment)


@mcp.tool()
async def qa_add_comment(issue_key: str, comment: str) -> dict[str, Any]:
    """Add a comment to any Jira ticket."""
    jira = get_jira()
    return await jira.add_comment(issue_key, comment)


@mcp.tool()
async def qa_get_issue_details(issue_key: str) -> dict[str, Any]:
    """Get full Jira issue details including description, comments, subtasks, and links."""
    jira = get_jira()
    try:
        issue = await jira.get_issue_full(issue_key)
        return {"status": "success", "issue": issue}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@mcp.tool()
async def qa_transition_ticket(issue_key: str, transition: str) -> dict[str, Any]:
    """Transition a Jira ticket to a new status without updating test result.
    
    Available transitions: backlog, grooming, open, in_progress, resolved, 
    blocked, pr_pending_review, reopened, closed, qa, beta_qa
    """
    jira = get_jira()
    try:
        return await jira.transition_issue(issue_key, transition)
    except ValueError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": f"Failed to transition: {e}"}


@mcp.tool()
async def qa_create_subtask(
    parent_key: str,
    summary: str,
    description: str = "",
) -> dict[str, Any]:
    """Create a subtask under a parent Jira issue."""
    jira = get_jira()
    try:
        result = await jira.create_subtask(parent_key, summary, description)
        if result:
            return {"status": "success", "parent_key": parent_key, "subtask": result}
        return {"status": "error", "error": "Failed to create subtask"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@mcp.tool()
async def qa_update_issue(
    issue_key: str,
    summary: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Update a Jira issue's summary and/or description."""
    jira = get_jira()
    try:
        return await jira.update_issue(issue_key, summary, description)
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ============================================================================
# AI-POWERED ANALYSIS TOOLS
# ============================================================================


@mcp.tool()
async def qa_generate_test_cases(
    issue_key: str,
    title: str = "",
    description: str = "",
) -> dict[str, Any]:
    """Generate test cases for a Jira ticket using AI."""
    handlers = get_handlers()
    if handlers is None:
        return {"status": "error", "error": "AI client not available"}

    if not title or not description:
        jira = get_jira()
        issue = await jira.get_issue(issue_key)
        if issue:
            title = title or issue["fields"]["summary"]
            description = description or issue["fields"].get("description", "")

    request_data = {"ticketKey": issue_key, "title": title, "description": description}
    result = handlers["test_cases"].handle_test_cases(request_data)
    return {"status": "success", "issue_key": issue_key, "test_cases": result}


@mcp.tool()
async def qa_summarize_comments(issue_key: str) -> dict[str, Any]:
    """Get a TLDR summary of all comments on a Jira ticket."""
    handlers = get_handlers()
    if handlers is None:
        return {"status": "error", "error": "AI client not available"}

    jira = get_jira()
    issue = await jira.get_issue(issue_key)
    if not issue:
        return {"status": "error", "error": f"Issue {issue_key} not found"}

    comments = [
        {"author": c.get("author", {}).get("displayName", "Unknown"), "content": c.get("body", "")}
        for c in issue["fields"].get("comment", {}).get("comments", [])
    ]

    request_data = {
        "ticketKey": issue_key,
        "title": issue["fields"]["summary"],
        "description": issue["fields"].get("description", ""),
        "comments": comments,
    }
    result = handlers["comment_summary"].handle_comment_summary(request_data)
    return {"status": "success", "issue_key": issue_key, "summary": result}


@mcp.tool()
async def qa_root_cause_analysis(
    issue_key: str,
    title: str = "",
    description: str = "",
) -> dict[str, Any]:
    """Analyze why a bug occurred using AI."""
    handlers = get_handlers()
    if handlers is None:
        return {"status": "error", "error": "AI client not available"}

    if not title or not description:
        jira = get_jira()
        issue = await jira.get_issue(issue_key)
        if issue:
            title = title or issue["fields"]["summary"]
            description = description or issue["fields"].get("description", "")

    request_data = {"ticketKey": issue_key, "title": title, "description": description}
    result = handlers["root_cause"].handle_root_cause(request_data)
    return {"status": "success", "issue_key": issue_key, "analysis": result}


@mcp.tool()
async def qa_generate_reproduction_steps(
    issue_key: str,
    title: str = "",
    description: str = "",
) -> dict[str, Any]:
    """Generate step-by-step repro steps for a bug."""
    handlers = get_handlers()
    if handlers is None:
        return {"status": "error", "error": "AI client not available"}

    if not title or not description:
        jira = get_jira()
        issue = await jira.get_issue(issue_key)
        if issue:
            title = title or issue["fields"]["summary"]
            description = description or issue["fields"].get("description", "")

    request_data = {"ticketKey": issue_key, "title": title, "description": description}
    result = handlers["reproduction_steps"].handle_reproduction_steps(request_data)
    return {"status": "success", "issue_key": issue_key, "steps": result}


@mcp.tool()
async def qa_analyze_story(issue_key: str) -> dict[str, Any]:
    """Analyze a user story for QA readiness."""
    handlers = get_handlers()
    if handlers is None:
        return {"status": "error", "error": "AI client not available"}

    jira = get_jira()
    issue = await jira.get_issue(issue_key)
    if not issue:
        return {"status": "error", "error": f"Issue {issue_key} not found"}

    comments = [
        {"author": c.get("author", {}).get("displayName", "Unknown"), "content": c.get("body", "")}
        for c in issue["fields"].get("comment", {}).get("comments", [])
    ]

    request_data = {
        "ticketKey": issue_key,
        "title": issue["fields"]["summary"],
        "description": issue["fields"].get("description", ""),
        "status": issue["fields"]["status"]["name"],
        "issueType": issue["fields"]["issuetype"]["name"],
        "comments": comments,
    }
    result = handlers["story_analysis"].handle(request_data)
    return {"status": "success", "issue_key": issue_key, "analysis": result}


@mcp.tool()
async def qa_analyze_epic(epic_key: str, primary_team: str = "") -> dict[str, Any]:
    """Analyze an epic for release readiness."""
    handlers = get_handlers()
    if handlers is None:
        return {"status": "error", "error": "AI client not available"}

    jira = get_jira()
    issue = await jira.get_issue(epic_key)
    if not issue:
        return {"status": "error", "error": f"Epic {epic_key} not found"}

    request_data = {
        "epicKey": epic_key,
        "ticketKey": epic_key,
        "title": issue["fields"]["summary"],
        "primaryOwningTeam": primary_team,
    }
    result = handlers["epic_analysis"].handle_epic_analysis(request_data)
    return {"status": "success", "epic_key": epic_key, "analysis": result}


# ============================================================================
# DEPLOYMENT VERIFICATION TOOLS
# ============================================================================


@mcp.tool()
async def qa_check_deployment(repo: str, environment: str) -> dict[str, Any]:
    """Check if code is deployed to an environment."""
    aws = get_aws()
    return aws.check_deployment(repo, environment)


@mcp.tool()
async def qa_get_deployment_summary(repo: str, environment: str) -> str:
    """Get a readable deployment status summary."""
    aws = get_aws()
    return aws.get_deployment_summary(repo, environment)


@mcp.tool()
async def qa_check_all_deployments(repo: str, environment: str) -> dict[str, Any]:
    """Check deployment status for ALL Lambda functions in a repo."""
    aws = get_aws()
    result = aws.check_deployment(repo, environment)
    if result["status"] == "error":
        return result

    functions = result.get("functions", [])
    if functions:
        latest = max(f.get("last_modified", "") for f in functions)
        oldest = min(f.get("last_modified", "") for f in functions)
        result["summary"] = {
            "total_functions": len(functions),
            "latest_deploy": latest,
            "oldest_deploy": oldest,
            "all_same_version": latest == oldest,
        }
    return result


@mcp.tool()
async def qa_compare_environments(repo: str, env1_name: str, env2_name: str) -> dict[str, Any]:
    """Compare deployments between two environments."""
    aws = get_aws()
    env1_result = aws.check_deployment(repo, env1_name)
    env2_result = aws.check_deployment(repo, env2_name)

    comparison = {
        "status": "success",
        "repo": repo,
        env1_name: {"status": env1_result.get("status"), "latest_deploy": None},
        env2_name: {"status": env2_result.get("status"), "latest_deploy": None},
    }

    if env1_result.get("status") == "success" and env1_result.get("functions"):
        comparison[env1_name]["latest_deploy"] = max(f["last_modified"] for f in env1_result["functions"])

    if env2_result.get("status") == "success" and env2_result.get("functions"):
        comparison[env2_name]["latest_deploy"] = max(f["last_modified"] for f in env2_result["functions"])

    return comparison


# ============================================================================
# JENKINS TOOLS
# ============================================================================


@mcp.tool()
async def qa_check_e2e_tests(repo: str) -> dict[str, Any]:
    """Check end-to-end test results from Jenkins."""
    jenkins = get_jenkins()
    return await jenkins.check_e2e_tests(repo)


@mcp.tool()
async def qa_get_recent_builds(repo: str, job_type: str = "e2e", count: int = 5) -> dict[str, Any]:
    """Get recent Jenkins build history."""
    jenkins = get_jenkins()
    return await jenkins.get_recent_builds(repo, job_type, count)


@mcp.tool()
async def qa_get_my_test_builds(username: str, view_name: str = "Test Builds") -> dict[str, Any]:
    """Get your personal Jenkins view showing test build status."""
    jenkins = get_jenkins()
    result = await jenkins.get_user_view(username, view_name)
    if result["status"] == "success":
        jobs = result["jobs"]
        result["summary"] = {
            "passing": sum(1 for j in jobs if j["status"] == "passing"),
            "failing": sum(1 for j in jobs if j["status"] == "failing"),
            "running": sum(1 for j in jobs if j["status"] == "running"),
        }
    return result


@mcp.tool()
async def qa_trigger_e2e_tests(
    repo: str,
    branch: str = "",
    pr_number: int = 0,
    environment: str = "",
    execution_mode: str = "",
) -> dict[str, Any]:
    """Trigger E2E tests for a repository with a custom branch or PR."""
    if pr_number > 0:
        github = get_github()
        pr_info = await github.get_pr(os.getenv("GITHUB_ORG", ""), repo, pr_number)
        if pr_info["status"] != "success":
            return {"status": "error", "error": f"Failed to get PR info: {pr_info.get('error')}"}
        branch = pr_info.get("head_branch", "")
        if not branch:
            return {"status": "error", "error": f"Could not get branch name from PR #{pr_number}"}

    if not branch:
        branch = "main"

    jenkins = get_jenkins()
    result = await jenkins.trigger_e2e_test(repo, branch, environment, execution_mode)
    if pr_number > 0:
        result["pr_number"] = pr_number
    return result


# ============================================================================
# GITHUB TOOLS
# ============================================================================


@mcp.tool()
async def qa_get_pr_info(owner: str, repo: str, pr_number: int) -> dict[str, Any]:
    """Get pull request details from GitHub."""
    github = get_github()
    return await github.get_pr(owner, repo, pr_number)


@mcp.tool()
async def qa_find_pr_for_commit(owner: str, repo: str, commit_sha: str) -> dict[str, Any]:
    """Find which pull request introduced a commit."""
    github = get_github()
    return await github.find_pr_for_commit(owner, repo, commit_sha)


@mcp.tool()
async def qa_check_dependabot_alerts(owner: str, repo: str) -> dict[str, Any]:
    """Check security vulnerabilities in a repository."""
    github = get_github()
    return await github.check_dependabot_alerts(owner, repo)


@mcp.tool()
async def qa_find_prs_for_ticket(issue_key: str, owner: str = "") -> dict[str, Any]:
    """Find GitHub PRs associated with a Jira ticket."""
    github = get_github()
    repos = os.getenv("GITHUB_REPOS", "").split(",") if os.getenv("GITHUB_REPOS") else []
    found_prs = []

    for repo in repos:
        repo = repo.strip()
        if not repo:
            continue
        try:
            prs = await github.search_prs(owner or os.getenv("GITHUB_ORG", ""), repo, issue_key)
            for pr in prs:
                found_prs.append({
                    "repo": repo,
                    "number": pr.get("number"),
                    "title": pr.get("title"),
                    "state": pr.get("state"),
                    "merged": pr.get("merged", False),
                })
        except Exception as e:
            logger.debug(f"Error searching {repo}: {e}")

    return {"status": "success", "issue_key": issue_key, "prs_found": len(found_prs), "prs": found_prs}


@mcp.tool()
async def qa_get_ticket_context(issue_key: str, owner: str = "") -> dict[str, Any]:
    """Get comprehensive ticket context including Jira details, linked PRs, and deployment status."""
    jira = get_jira()
    github = get_github()
    aws = get_aws()

    context = {"status": "success", "issue_key": issue_key, "ticket": None, "prs": [], "deployments": {}}

    issue = await jira.get_issue(issue_key)
    if not issue:
        return {"status": "error", "error": f"Issue {issue_key} not found"}

    context["ticket"] = {
        "key": issue["key"],
        "summary": issue["fields"]["summary"],
        "type": issue["fields"]["issuetype"]["name"],
        "status": issue["fields"]["status"]["name"],
    }

    repos = os.getenv("GITHUB_REPOS", "").split(",") if os.getenv("GITHUB_REPOS") else []
    for repo in repos:
        repo = repo.strip()
        if not repo:
            continue
        try:
            prs = await github.search_prs(owner or os.getenv("GITHUB_ORG", ""), repo, issue_key)
            for pr in prs:
                context["prs"].append({
                    "repo": repo,
                    "number": pr.get("number"),
                    "title": pr.get("title"),
                    "merged": pr.get("merged", False),
                })
                if pr.get("merged"):
                    deploy_check = aws.check_deployment(repo, os.getenv("DEFAULT_ENVIRONMENT", ""))
                    if deploy_check.get("status") == "success":
                        context["deployments"][repo] = {"deployed": True}
        except Exception as e:
            logger.debug(f"Error checking {repo}: {e}")

    has_merged_pr = any(pr.get("merged") for pr in context["prs"])
    has_deployment = bool(context["deployments"])

    if has_merged_pr and has_deployment:
        context["readiness"] = "Ready for QA - PR merged and code deployed"
    elif has_merged_pr:
        context["readiness"] = "PR merged but deployment not verified"
    elif context["prs"]:
        context["readiness"] = "PR found but not yet merged"
    else:
        context["readiness"] = "No PR found"

    return context


# ============================================================================
# WEBEX TOOLS
# ============================================================================


@mcp.tool()
async def webex_list_rooms(max_rooms: int = 50) -> dict[str, Any]:
    """List all Webex rooms/spaces the bot has access to."""
    webex = get_webex()
    return await webex.list_rooms(max_rooms)


@mcp.tool()
async def webex_get_messages(room_id: str = "", room_name: str = "", max_messages: int = 30) -> dict[str, Any]:
    """Get recent messages from a Webex room."""
    webex = get_webex()

    if room_name and not room_id:
        room = await webex.get_room_by_title(room_name)
        if not room:
            return {"status": "error", "error": f"No room found matching '{room_name}'"}
        room_id = room["id"]

    if not room_id:
        return {"status": "error", "error": "Provide either room_id or room_name"}

    return await webex.get_messages(room_id, max_messages)


@mcp.tool()
async def webex_post_message(
    room_id: str = "",
    room_name: str = "",
    message: str = "",
    markdown: str = "",
) -> dict[str, Any]:
    """Post a message to a Webex room."""
    webex = get_webex()

    if room_name and not room_id:
        room = await webex.get_room_by_title(room_name)
        if not room:
            return {"status": "error", "error": f"No room found matching '{room_name}'"}
        room_id = room["id"]

    if not room_id:
        return {"status": "error", "error": "Provide either room_id or room_name"}

    if not message and not markdown:
        return {"status": "error", "error": "Provide either message or markdown content"}

    return await webex.post_message(room_id, message, markdown)


@mcp.tool()
async def webex_search_messages(
    search_term: str,
    room_id: str = "",
    room_name: str = "",
    max_messages: int = 100,
) -> dict[str, Any]:
    """Search for messages containing a term in a Webex room."""
    webex = get_webex()

    if room_name and not room_id:
        room = await webex.get_room_by_title(room_name)
        if not room:
            return {"status": "error", "error": f"No room found matching '{room_name}'"}
        room_id = room["id"]

    if not room_id:
        return {"status": "error", "error": "Provide either room_id or room_name"}

    return await webex.search_messages(room_id, search_term, max_messages)


@mcp.tool()
async def webex_summarize_room(
    room_id: str = "",
    room_name: str = "",
    max_messages: int = 30,
) -> dict[str, Any]:
    """Get a summary of recent conversation in a Webex room."""
    webex = get_webex()

    if room_name and not room_id:
        room = await webex.get_room_by_title(room_name)
        if not room:
            return {"status": "error", "error": f"No room found matching '{room_name}'"}
        room_id = room["id"]
        room_title = room["title"]
    else:
        room_title = "Unknown"

    if not room_id:
        return {"status": "error", "error": "Provide either room_id or room_name"}

    summary_data = await webex.get_room_summary(room_id, max_messages)
    if summary_data["status"] != "success":
        return summary_data

    conversation = summary_data["conversation"]
    if not conversation:
        return {"status": "success", "room": room_title, "summary": "No messages to summarize."}

    ai_client = get_ai_client()
    if ai_client:
        try:
            prompt = f"""Summarize this Webex conversation. Focus on:
- Key decisions made
- Action items or tasks mentioned
- Important announcements
- Questions that need answers

Conversation from '{room_title}':
{conversation}

Provide a concise bullet-point summary."""
            summary = ai_client.ask_openai(prompt)
            return {
                "status": "success",
                "room": room_title,
                "message_count": summary_data["message_count"],
                "summary": summary,
            }
        except Exception as e:
            logger.warning(f"AI summarization failed: {e}")

    return {
        "status": "success",
        "room": room_title,
        "message_count": summary_data["message_count"],
        "note": "AI unavailable - returning raw messages",
        "conversation": conversation,
    }


@mcp.tool()
async def webex_whoami() -> dict[str, Any]:
    """Get info about the authenticated Webex bot/user."""
    webex = get_webex()
    return await webex.get_my_info()


# ============================================================================
# MAIN
# ============================================================================


if __name__ == "__main__":
    mcp.run(log_level="WARNING")
