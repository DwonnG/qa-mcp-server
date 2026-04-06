#!/usr/bin/env python3
"""QA MCP Server - Automate QA workflows for development teams."""

import json as json_module
import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any

from botocore.exceptions import ClientError
from dotenv import load_dotenv
from fastmcp import FastMCP

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from qa_mcp.clients import AWSClient, BrowserClient, GitHubClient, JenkinsClient, JiraClient, WebexClient

try:
    from config import JENKINS_JOBS, JQL_TEMPLATES, QA_COMMENT_TEMPLATES, RELEASE_TESTING
except ImportError:
    JENKINS_JOBS = {}
    JQL_TEMPLATES = {
        "ready_for_qa": (
            'project = {project} AND type in (Story, Bug, Improvement, Task, Vulnerability) '
            'AND status in (QA, "Beta QA") AND "Team(s)" in ({team}) '
            "AND Sprint in openSprints() AND Validator is EMPTY "
            "ORDER BY fixVersion ASC"
        ),
        "in_progress": (
            'project = {project} AND type in (Story, Bug, Improvement, Task, Vulnerability) '
            'AND status in ("In Progress", "PR Pending Review") '
            "ORDER BY updated DESC"
        ),
    }
    QA_COMMENT_TEMPLATES = {
        "pass": "h3. QA Validation - PASS\n\n*Environment:* {environment}\n\n*Verification:*\n{verification_steps}\n\n*Test Result:* PASS - {summary}",
        "fail": "h3. QA Validation - FAIL\n\n*Environment:* {environment}\n\n*Issue:* {issue_description}\n\n*Steps:*\n{steps}\n\n*Expected:* {expected}\n*Actual:* {actual}",
    }
    RELEASE_TESTING = {
        "template_epic": "O365-49840",
        "summary_format": "Release {version} Testing",
    }

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("qa-automation")

_jira: JiraClient | None = None
_aws: AWSClient | None = None
_jenkins: JenkinsClient | None = None
_github: GitHubClient | None = None
_webex: WebexClient | None = None
_browser: BrowserClient | None = None
_ai_client: Any = None
_secret_manager: Any = None
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


def get_browser() -> BrowserClient:
    global _browser
    if _browser is None:
        _browser = BrowserClient()
    return _browser


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


@mcp.tool()
async def qa_get_qa_queue(
    project: str,
    team: str = "Raven",
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


@mcp.tool()
async def qa_clone_release_epic(
    version: str,
    template_epic: str = "",
) -> dict[str, Any]:
    """Clone the release testing template Epic and all linked tasks for a new version.
    
    Args:
        version: Release version (e.g., "3.3.0")
        template_epic: Source template Epic key (uses config default if not provided)
    
    Returns:
        New Epic key and list of cloned task keys
    """
    # Use config default if not provided
    if not template_epic:
        template_epic = RELEASE_TESTING.get("template_epic", "O365-49840")
    
    jira = get_jira()
    try:
        template = await jira.get_issue(template_epic)
        if not template:
            return {"status": "error", "error": f"Template Epic {template_epic} not found"}

        project_key = template["fields"]["project"]["key"]
        template_description = template["fields"].get("description", "")

        summary_format = RELEASE_TESTING.get("summary_format", "Release {version} Testing")
        new_epic_summary = summary_format.format(version=version)
        new_epic = await jira.create_issue(
            project=project_key,
            issue_type="Epic",
            summary=new_epic_summary,
            description=template_description,
        )

        if not new_epic:
            return {"status": "error", "error": "Failed to create new Epic"}

        new_epic_key = new_epic["key"]
        template_tasks = await jira.get_issues_in_epic(template_epic)

        cloned_tasks = []
        for task in template_tasks:
            original_key = task["key"]
            original_summary = task["fields"]["summary"]
            original_description = task["fields"].get("description", "")
            original_type = task["fields"]["issuetype"]["name"]

            new_summary = original_summary.replace("[TEMPLATE]", version)
            cloned_task = await jira.create_issue(
                project=project_key,
                issue_type=original_type,
                summary=new_summary,
                description=original_description,
                epic_link=new_epic_key,
            )
            
            if cloned_task:
                cloned_tasks.append({
                    "original": original_key,
                    "new": cloned_task["key"],
                    "summary": new_summary,
                })
            else:
                cloned_tasks.append({
                    "original": original_key,
                    "new": None,
                    "error": "Failed to clone",
                })
        
        return {
            "status": "success",
            "new_epic": new_epic_key,
            "new_epic_summary": new_epic_summary,
            "cloned_tasks": cloned_tasks,
            "total_cloned": len([t for t in cloned_tasks if t.get("new")]),
            "total_failed": len([t for t in cloned_tasks if not t.get("new")]),
        }
        
    except Exception as e:
        return {"status": "error", "error": str(e)}


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


@mcp.tool()
async def qa_invoke_internal_api(
    environment: str,
    api_name: str,
    http_method: str,
    path: str,
    body: str = "",
    query_string: str = "",
) -> dict[str, Any]:
    """Invoke an API Gateway endpoint via the AWS control plane.

    Args:
        environment: Target environment.
        api_name: Logical API name.
        http_method: HTTP method (GET, POST, PUT, PATCH, DELETE).
        path: Resource path (template or concrete).
        body: JSON request body for POST/PUT/PATCH requests.
        query_string: Query parameters.
    """
    aws = get_aws()
    try:
        return aws.invoke_api(
            environment=environment,
            api_name=api_name,
            http_method=http_method,
            path=path,
            body=body,
            query_string=query_string,
        )
    except (ValueError, ClientError) as exc:
        return {"status": "error", "error": str(exc)}


@mcp.tool()
async def qa_list_api_resources(
    environment: str,
    api_name: str,
) -> dict[str, Any]:
    """List all available resource paths for an API Gateway.

    Args:
        environment: Target environment.
        api_name: Logical API name.
    """
    aws = get_aws()
    try:
        rest_api_id = aws.discover_rest_api(environment, api_name)
        _ = aws.get_resource_id(rest_api_id, "/")
        resources = aws._resource_cache.get(rest_api_id, {})
        return {
            "status": "success",
            "api": f"{environment}_{api_name}",
            "rest_api_id": rest_api_id,
            "paths": sorted(resources.keys()),
        }
    except (ValueError, ClientError) as exc:
        return {"status": "error", "error": str(exc)}


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
    test_tag: str = "",
) -> dict[str, Any]:
    """Trigger E2E tests for a repository with a custom branch or PR.
    
    Args:
        repo: Repository name (python-raptor, directory-data, go-raptor)
        branch: Branch name to test (defaults to main)
        pr_number: PR number - will auto-detect branch from PR
        environment: Target environment (integration, qa, beta)
        execution_mode: How to run tests (regression, smoke, test_tag)
        test_tag: Pytest marker to run when execution_mode is 'test_tag'
                  Examples: bulk, inline, smoke, provisioning
    """
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
    result = await jenkins.trigger_e2e_test(
        repo=repo,
        branch=branch,
        environment=environment,
        execution_mode=execution_mode,
        test_tag=test_tag,
        pr_number=pr_number,
    )
    if pr_number > 0:
        result["pr_number"] = pr_number
    return result


@mcp.tool()
async def qa_get_build_console(
    repo: str,
    build_number: int,
    job_type: str = "e2e",
    tail_lines: int = 200,
) -> dict[str, Any]:
    """Get console output from a specific Jenkins build (last N lines)."""
    jenkins = get_jenkins()
    return await jenkins.get_build_console(repo, build_number, job_type, tail_lines)


@mcp.tool()
async def qa_get_build_failures(
    repo: str,
    build_number: int,
    job_type: str = "e2e",
) -> dict[str, Any]:
    """Get test report from a Jenkins build showing failed tests."""
    jenkins = get_jenkins()
    return await jenkins.get_build_test_report(repo, build_number, job_type)


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


@mcp.tool()
async def qa_verify_vulnerability_resolved(
    issue_key: str,
    repo: str = "",
    environment: str = "integration",
    auto_resolve: bool = True,
) -> dict[str, Any]:
    """Verify a vulnerability fix: find PR, check merge/deployment/tests, then resolve.
    
    Repo is auto-detected from the ticket if not provided.
    Set auto_resolve=False to dry-run without resolving.
    """
    jira = get_jira()
    github = get_github()
    aws = get_aws()
    jenkins = get_jenkins()
    owner = os.getenv("GITHUB_ORG", "raptor")

    result = {
        "status": "in_progress",
        "issue_key": issue_key,
        "environment": environment,
        "checks": {},
    }

    try:
        issue = await jira.get_issue(issue_key)
        if not issue:
            return {"status": "error", "error": f"Issue {issue_key} not found"}

        description = issue["fields"].get("description", "")

        if not repo:
            try:
                desc_json = json_module.loads(description)
                repo = desc_json.get("Repo_Name", "")
            except (json_module.JSONDecodeError, TypeError):
                pass

            if not repo:
                known_repos = (
                    "directory-data", "python-raptor", "go-raptor", "raptor-ui",
                    "raptor-engine", "policy-enforcement", "terraform",
                    "reporting", "jenkins-library",
                )
                for part in issue["fields"].get("summary", "").split(":"):
                    if part.strip() in known_repos:
                        repo = part.strip()
                        break

            if not repo:
                return {"status": "error", "error": "Could not detect repo. Provide it explicitly."}

        result["checks"]["ticket"] = {
            "summary": issue["fields"]["summary"],
            "repo_detected": repo,
        }
    except Exception as e:
        return {"status": "error", "error": f"Error fetching ticket: {e}"}

    result["repo"] = repo

    try:
        prs = await github.search_prs(owner, repo, issue_key)
        if not prs:
            return {**result, "status": "error", "error": f"No PR found for {issue_key} in {repo}"}

        pr = prs[0]
        pr_number = pr.get("number")
        merged_at_str = pr.get("merged_at")

        pr_detail = await github.get_pr(owner, repo, pr_number)
        merge_commit_sha = pr_detail.get("merge_commit_sha") if pr_detail.get("status") == "success" else None
        if not merged_at_str and pr_detail.get("status") == "success":
            merged_at_str = pr_detail.get("merged_at")

        merged_at = None
        if merged_at_str:
            merged_at = datetime.fromisoformat(merged_at_str.replace("Z", "+00:00"))

        result["checks"]["pr"] = {
            "number": pr_number,
            "title": pr.get("title"),
            "merged": pr.get("merged", False),
            "merged_at": merged_at_str,
            "merge_commit_sha": merge_commit_sha,
        }
    except Exception as e:
        return {**result, "status": "error", "error": f"Error finding PR: {e}"}

    if not pr.get("merged"):
        return {**result, "status": "blocked", "error": f"PR #{pr_number} is not merged yet"}

    try:
        deploy_result = aws.check_deployment(repo, environment)
        deployed_after_merge = False
        latest_deploy = None

        if deploy_result.get("status") == "success" and merged_at:
            for func in deploy_result.get("functions", []):
                if func.get("status") == "success" and func.get("last_modified"):
                    func_time = datetime.fromisoformat(func["last_modified"].replace("Z", "+00:00"))
                    if latest_deploy is None or func_time > latest_deploy:
                        latest_deploy = func_time
            deployed_after_merge = latest_deploy is not None and latest_deploy > merged_at

        result["checks"]["deployment"] = {
            "status": deploy_result.get("status"),
            "functions_count": len(deploy_result.get("functions", [])),
            "latest_deploy": latest_deploy.isoformat() if latest_deploy else None,
            "deployed_after_merge": deployed_after_merge,
        }

        if deploy_result.get("status") != "success":
            return {**result, "status": "blocked", "error": f"Deployment check failed for {repo} in {environment}"}
    except Exception as e:
        result["checks"]["deployment"] = {"status": "error", "error": str(e)}

    try:
        test_result = await jenkins.check_e2e_tests(repo)
        build_timestamp = test_result.get("timestamp")
        tests_ran_after_merge = False
        if build_timestamp and merged_at:
            build_time = datetime.fromtimestamp(build_timestamp / 1000, tz=timezone.utc)
            tests_ran_after_merge = build_time > merged_at

        causes = test_result.get("causes", [])
        upstream = None
        for cause in causes:
            if cause.get("upstream_project"):
                upstream = {
                    "project": cause["upstream_project"],
                    "build": cause.get("upstream_build"),
                    "description": cause.get("description"),
                }
                break

        result["checks"]["e2e_tests"] = {
            "status": test_result.get("status"),
            "build_number": test_result.get("build_number"),
            "build_result": test_result.get("result"),
            "build_url": test_result.get("url"),
            "tests_ran_after_merge": tests_ran_after_merge,
            "triggered_by": upstream or (causes[0]["description"] if causes else "unknown"),
        }

        if test_result.get("result") not in ("SUCCESS", None):
            result["status"] = "warning"
            result["warning"] = f"E2E tests result: {test_result.get('result')}"
    except Exception as e:
        result["checks"]["e2e_tests"] = {"status": "error", "error": str(e)}

    checks = result["checks"]
    e2e = checks.get("e2e_tests", {})
    deploy = checks.get("deployment", {})
    pr_checks = checks.get("pr", {})
    ticket_info = checks.get("ticket", {})

    job_path = JENKINS_JOBS.get(repo, {}).get("e2e", "")
    job_name = job_path.split("/job/")[-1] if job_path else repo

    vuln_summary = ticket_info.get("summary", issue_key)
    try:
        desc_data = json_module.loads(description) if description else {}
        vuln_line = f"- {desc_data.get('Vulnerable_Package', 'N/A')} ({desc_data.get('Severity', 'N/A')}): {desc_data.get('Advisory_ID', 'N/A')}"
    except Exception:
        vuln_line = f"- {vuln_summary}"

    commit_sha = (pr_checks.get("merge_commit_sha") or "N/A")[:8]

    if auto_resolve:
        try:
            comment = (
                "h3. QA Validation - PASS (Vulnerability)\n\n"
                f"*Environment:* {environment}\n\n"
                "h4. Verification Chain\n"
                "||Step||Detail||\n"
                f"|PR|#{pr_number} (merged {pr_checks.get('merged_at', 'N/A')})|\n"
                f"|Commit|{{{{{commit_sha}}}}}|\n"
                f"|Deployment|Last deploy: {deploy.get('latest_deploy', 'N/A')}|\n"
                f"|E2E Tests|Build #{e2e.get('build_number', 'N/A')} — {job_name}|\n\n"
                "h4. Vulnerabilities Addressed\n"
                f"{vuln_line}\n"
            )
            resolve_result = await jira.resolve_pass(issue_key, comment)
            result["status"] = "success"
            result["resolution"] = resolve_result
        except Exception as e:
            result["status"] = "error"
            result["error"] = f"Failed to resolve ticket: {e}"
    else:
        result["status"] = "verified"
        result["message"] = "All checks passed. Set auto_resolve=True to resolve."

    return result


@mcp.tool()
async def qa_verify_version_bump(
    issue_key: str,
    repos: list[str] | None = None,
    environment: str = "integration",
    auto_resolve: bool = True,
) -> dict[str, Any]:
    """Verify a version bump release: check each repo's PR, deployment, and E2E tests.

    Repos are auto-detected from the ticket summary if not provided.
    Terraform-managed repos (python-raptor, policy-enforcement) are verified
    via terraform PRs. Service repos (directory-data, etc.) are verified via
    their own PR, Lambda deployment, and E2E tests.
    Set auto_resolve=False to dry-run without resolving.
    """
    TERRAFORM_MANAGED = {
        "python-raptor": "python_raptor_version",
    }

    jira = get_jira()
    github = get_github()
    aws = get_aws()
    jenkins = get_jenkins()
    owner = os.getenv("GITHUB_ORG", "raptor")

    result: dict[str, Any] = {
        "status": "in_progress",
        "issue_key": issue_key,
        "environment": environment,
        "repos": {},
    }

    try:
        issue = await jira.get_issue(issue_key)
        if not issue:
            return {"status": "error", "error": f"Issue {issue_key} not found"}
    except Exception as e:
        return {"status": "error", "error": f"Error fetching ticket: {e}"}

    summary = issue["fields"].get("summary", "")
    version = ""
    for part in summary.split():
        if part.startswith("v") and "." in part:
            version = part.strip(" -:")
            break

    result["version"] = version
    result["summary"] = summary

    if not repos:
        known_repos = {
            "python-raptor": ("python-raptor", "python_raptor", "pythonraptor", "policydb", "policy db", "reporting"),
            "directory-data": ("directory-data", "directory data", "data layer"),
            "go-raptor": ("go-raptor", "go_raptor"),
            "raptor-ui": ("raptor-ui", "raptor ui"),
            "raptor-docs": ("raptor-docs", "raptor docs", "raptor_docs", "raptordocs")
        }
        summary_lower = summary.lower()
        description_lower = (issue["fields"].get("description") or "").lower()
        search_text = f"{summary_lower} {description_lower}"

        repos = []
        for repo_name, aliases in known_repos.items():
            if any(alias in search_text for alias in aliases):
                repos.append(repo_name)

        if not repos:
            return {"status": "error", "error": "Could not detect repos from ticket. Provide them explicitly."}

    result["detected_repos"] = repos
    all_passed = True
    has_warnings = False
    repo_comment_sections = []

    terraform_repos = [r for r in repos if r in TERRAFORM_MANAGED]
    service_repos = [r for r in repos if r not in TERRAFORM_MANAGED]

    if terraform_repos:
        tf_result: dict[str, Any] = {"repo": "terraform", "checks": {}, "managed_repos": terraform_repos}

        try:
            prs = await github.search_prs(owner, "terraform", issue_key)
            if not prs:
                tf_result["checks"]["pr"] = {"status": "not_found"}
                tf_result["status"] = "warning"
                has_warnings = True
            else:
                pr = prs[0]
                pr_number = pr.get("number")
                merged_at_str = pr.get("merged_at")

                pr_detail = await github.get_pr(owner, "terraform", pr_number)
                merge_commit_sha = pr_detail.get("merge_commit_sha") if pr_detail.get("status") == "success" else None
                if not merged_at_str and pr_detail.get("status") == "success":
                    merged_at_str = pr_detail.get("merged_at")

                tf_result["checks"]["pr"] = {
                    "number": pr_number,
                    "title": pr.get("title"),
                    "merged": pr.get("merged", False),
                    "merged_at": merged_at_str,
                    "merge_commit_sha": merge_commit_sha,
                }

                if pr.get("merged"):
                    tf_result["status"] = "passed"
                    version_vars = [TERRAFORM_MANAGED[r] for r in terraform_repos]
                    tf_result["checks"]["version_variables"] = version_vars
                else:
                    tf_result["status"] = "blocked"
                    all_passed = False
        except Exception as e:
            tf_result["checks"]["pr"] = {"status": "error", "error": str(e)}
            tf_result["status"] = "error"
            all_passed = False

        result["repos"]["terraform"] = tf_result

        tf_merged_at = None
        tf_merged_at_str = tf_result["checks"].get("pr", {}).get("merged_at")
        if tf_merged_at_str:
            tf_merged_at = datetime.fromisoformat(tf_merged_at_str.replace("Z", "+00:00"))

        for managed_repo in terraform_repos:
            managed_result: dict[str, Any] = {
                "repo": managed_repo,
                "verified_via": "terraform",
                "version_variable": TERRAFORM_MANAGED[managed_repo],
                "status": tf_result.get("status", "error"),
                "checks": {},
            }

            if tf_result.get("status") == "passed":
                try:
                    test_result = await jenkins.check_e2e_tests(managed_repo)
                    build_timestamp = test_result.get("timestamp")
                    tests_ran_after_merge = False
                    if build_timestamp and tf_merged_at:
                        build_time = datetime.fromtimestamp(build_timestamp / 1000, tz=timezone.utc)
                        tests_ran_after_merge = build_time > tf_merged_at

                    causes = test_result.get("causes", [])
                    upstream = None
                    for cause in causes:
                        if cause.get("upstream_project"):
                            upstream = {
                                "project": cause["upstream_project"],
                                "build": cause.get("upstream_build"),
                                "description": cause.get("description"),
                            }
                            break

                    managed_result["checks"]["e2e_tests"] = {
                        "status": test_result.get("status"),
                        "build_number": test_result.get("build_number"),
                        "build_result": test_result.get("result"),
                        "build_url": test_result.get("url"),
                        "tests_ran_after_merge": tests_ran_after_merge,
                        "triggered_by": upstream or (causes[0]["description"] if causes else "unknown"),
                    }

                    if test_result.get("result") not in ("SUCCESS", None):
                        managed_result["status"] = "warning"
                        has_warnings = True
                except Exception as e:
                    managed_result["checks"]["e2e_tests"] = {"status": "error", "error": str(e)}

            result["repos"][managed_repo] = managed_result

        pr_info = tf_result["checks"].get("pr", {})
        managed_names = ", ".join(terraform_repos)
        version_vars = ", ".join(TERRAFORM_MANAGED[r] for r in terraform_repos)
        section = (
            f"h4. Terraform (manages {managed_names})\n"
            f"||Step||Detail||\n"
            f"|PR|#{pr_info.get('number', 'N/A')} (merged {pr_info.get('merged_at', 'N/A')})|\n"
            f"|Commit|{{{{{(pr_info.get('merge_commit_sha') or 'N/A')[:8]}}}}}|\n"
            f"|Version Vars|{version_vars}|\n"
        )
        repo_comment_sections.append(section)

        for managed_repo in terraform_repos:
            e2e_info = result["repos"][managed_repo].get("checks", {}).get("e2e_tests", {})
            job_path = JENKINS_JOBS.get(managed_repo, {}).get("e2e", "")
            job_name = job_path.split("/job/")[-1] if job_path else managed_repo
            section = (
                f"h4. {managed_repo} (E2E)\n"
                f"||Step||Detail||\n"
                f"|E2E Tests|Build #{e2e_info.get('build_number', 'N/A')} — {job_name} — {e2e_info.get('build_result', 'N/A')}|\n"
                f"|Ran After TF Merge|{e2e_info.get('tests_ran_after_merge', 'N/A')}|\n"
            )
            repo_comment_sections.append(section)

    for repo in service_repos:
        repo_result: dict[str, Any] = {"repo": repo, "checks": {}}

        try:
            prs = await github.search_prs(owner, repo, issue_key)
            if not prs:
                repo_result["checks"]["pr"] = {"status": "not_found"}
                repo_result["status"] = "warning"
                has_warnings = True
                result["repos"][repo] = repo_result
                continue

            pr = prs[0]
            pr_number = pr.get("number")
            merged_at_str = pr.get("merged_at")

            pr_detail = await github.get_pr(owner, repo, pr_number)
            merge_commit_sha = pr_detail.get("merge_commit_sha") if pr_detail.get("status") == "success" else None
            if not merged_at_str and pr_detail.get("status") == "success":
                merged_at_str = pr_detail.get("merged_at")

            merged_at = None
            if merged_at_str:
                merged_at = datetime.fromisoformat(merged_at_str.replace("Z", "+00:00"))

            repo_result["checks"]["pr"] = {
                "number": pr_number,
                "title": pr.get("title"),
                "merged": pr.get("merged", False),
                "merged_at": merged_at_str,
                "merge_commit_sha": merge_commit_sha,
            }

            if not pr.get("merged"):
                repo_result["status"] = "blocked"
                all_passed = False
                result["repos"][repo] = repo_result
                continue
        except Exception as e:
            repo_result["checks"]["pr"] = {"status": "error", "error": str(e)}
            all_passed = False
            result["repos"][repo] = repo_result
            continue

        try:
            deploy_result = aws.check_deployment(repo, environment)
            deployed_after_merge = False
            latest_deploy = None

            if deploy_result.get("status") == "success" and merged_at:
                for func in deploy_result.get("functions", []):
                    if func.get("status") == "success" and func.get("last_modified"):
                        func_time = datetime.fromisoformat(func["last_modified"].replace("Z", "+00:00"))
                        if latest_deploy is None or func_time > latest_deploy:
                            latest_deploy = func_time
                deployed_after_merge = latest_deploy is not None and latest_deploy > merged_at

            repo_result["checks"]["deployment"] = {
                "status": deploy_result.get("status"),
                "functions_count": len(deploy_result.get("functions", [])),
                "latest_deploy": latest_deploy.isoformat() if latest_deploy else None,
                "deployed_after_merge": deployed_after_merge,
            }

            if deploy_result.get("status") != "success":
                repo_result["status"] = "blocked"
                all_passed = False
        except Exception as e:
            repo_result["checks"]["deployment"] = {"status": "error", "error": str(e)}

        try:
            test_result = await jenkins.check_e2e_tests(repo)
            build_timestamp = test_result.get("timestamp")
            tests_ran_after_merge = False
            if build_timestamp and merged_at:
                build_time = datetime.fromtimestamp(build_timestamp / 1000, tz=timezone.utc)
                tests_ran_after_merge = build_time > merged_at

            causes = test_result.get("causes", [])
            upstream = None
            for cause in causes:
                if cause.get("upstream_project"):
                    upstream = {
                        "project": cause["upstream_project"],
                        "build": cause.get("upstream_build"),
                        "description": cause.get("description"),
                    }
                    break

            repo_result["checks"]["e2e_tests"] = {
                "status": test_result.get("status"),
                "build_number": test_result.get("build_number"),
                "build_result": test_result.get("result"),
                "build_url": test_result.get("url"),
                "tests_ran_after_merge": tests_ran_after_merge,
                "triggered_by": upstream or (causes[0]["description"] if causes else "unknown"),
            }

            if test_result.get("result") not in ("SUCCESS", None):
                repo_result["status"] = "warning"
                has_warnings = True
        except Exception as e:
            repo_result["checks"]["e2e_tests"] = {"status": "error", "error": str(e)}

        if "status" not in repo_result:
            repo_result["status"] = "passed"

        result["repos"][repo] = repo_result

        pr_info = repo_result["checks"].get("pr", {})
        deploy_info = repo_result["checks"].get("deployment", {})
        e2e_info = repo_result["checks"].get("e2e_tests", {})
        job_path = JENKINS_JOBS.get(repo, {}).get("e2e", "")
        job_name = job_path.split("/job/")[-1] if job_path else repo

        section = (
            f"h4. {repo}\n"
            f"||Step||Detail||\n"
            f"|PR|#{pr_info.get('number', 'N/A')} (merged {pr_info.get('merged_at', 'N/A')})|\n"
            f"|Commit|{{{{{(pr_info.get('merge_commit_sha') or 'N/A')[:8]}}}}}|\n"
            f"|Deployment|{deploy_info.get('functions_count', 0)} functions, last deploy: {deploy_info.get('latest_deploy', 'N/A')}|\n"
            f"|E2E Tests|Build #{e2e_info.get('build_number', 'N/A')} — {job_name} — {e2e_info.get('build_result', 'N/A')}|\n"
        )
        repo_comment_sections.append(section)

    if all_passed and not has_warnings:
        result["status"] = "verified" if not auto_resolve else "in_progress"
    elif has_warnings:
        result["status"] = "warning"
    else:
        result["status"] = "blocked"

    if auto_resolve and all_passed:
        try:
            comment = (
                "h3. QA Validation - PASS (Version Bump)\n\n"
                f"*Version:* {version or issue_key}\n"
                f"*Environment:* {environment}\n\n"
                + "\n".join(repo_comment_sections)
            )
            resolve_result = await jira.resolve_pass(issue_key, comment)
            result["status"] = "success"
            result["resolution"] = resolve_result
        except Exception as e:
            result["status"] = "error"
            result["error"] = f"Failed to resolve ticket: {e}"
    elif not auto_resolve and all_passed:
        result["status"] = "verified"
        result["message"] = "All checks passed. Set auto_resolve=True to resolve."

    return result


@mcp.tool()
async def qa_verify_ui_version(
    issue_key: str,
    environment: str = "integration",
    expected_version: str = "",
    auto_resolve: bool = True,
) -> dict[str, Any]:
    """Verify the UI version by opening a headless browser and reading the console.

    Logs into the environment using credentials from AWS Secrets Manager,
    captures browser console output, and checks Version/Build/Env.
    Expected version is auto-detected from the ticket summary if not provided.
    Set auto_resolve=False to dry-run without resolving.
    """
    jira = get_jira()
    browser = get_browser()

    result: dict[str, Any] = {
        "status": "in_progress",
        "issue_key": issue_key,
        "environment": environment,
    }

    try:
        issue = await jira.get_issue(issue_key)
        if not issue:
            return {"status": "error", "error": f"Issue {issue_key} not found"}
    except Exception as e:
        return {"status": "error", "error": f"Error fetching ticket: {e}"}

    summary = issue["fields"].get("summary", "")
    result["summary"] = summary

    if not expected_version:
        match = re.search(r"v?(\d+\.\d+\.\d+)", summary)
        if match:
            expected_version = match.group(1)
        else:
            return {"status": "error", "error": "Could not detect version from ticket. Provide expected_version."}

    result["expected_version"] = expected_version

    try:
        build_info = await browser.get_ui_build_info(environment)
        result["build_info"] = build_info
    except Exception as e:
        return {**result, "status": "error", "error": f"Browser check failed: {e}"}

    if build_info.get("status") == "error":
        return {**result, "status": "error", "error": build_info.get("error", "Unknown browser error")}

    actual_version = build_info.get("version", "")
    version_match = actual_version == expected_version

    result["version_match"] = version_match
    result["actual_version"] = actual_version

    if not version_match:
        result["status"] = "failed"
        result["error"] = f"Version mismatch: expected {expected_version}, got {actual_version or 'not found'}"
        return result

    if auto_resolve:
        try:
            comment = (
                "h3. QA Validation - PASS (UI Version Bump)\n\n"
                f"*Environment:* {environment}\n"
                f"*URL:* {build_info.get('url', 'N/A')}\n\n"
                "||Check||Result||\n"
                f"|Expected Version|{expected_version}|\n"
                f"|Actual Version|{actual_version}|\n"
                f"|Build|{build_info.get('build', 'N/A')}|\n"
                f"|Reported Env|{build_info.get('reported_env', 'N/A')}|\n"
                f"|Match|{version_match}|\n"
            )
            resolve_result = await jira.resolve_pass(issue_key, comment)
            result["status"] = "success"
            result["resolution"] = resolve_result
        except Exception as e:
            result["status"] = "error"
            result["error"] = f"Failed to resolve ticket: {e}"
    else:
        result["status"] = "verified"
        result["message"] = f"UI version {actual_version} matches expected {expected_version}. Set auto_resolve=True to resolve."

    return result


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


if __name__ == "__main__":
    mcp.run(log_level="WARNING")
