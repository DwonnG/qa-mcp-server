"""
Example configuration for QA MCP Server.

Copy this file to config.py and customize for your organization.
"""

from typing import TypedDict


class JiraFieldIds(TypedDict):
    """Custom field IDs for Jira."""

    test_result: str
    validator: str
    team: str


JIRA_FIELDS: JiraFieldIds = {
    "test_result": "customfield_XXXXX",
    "validator": "customfield_XXXXX",
    "team": "customfield_XXXXX",
}

TEST_RESULT_VALUES = {
    "pass": {"id": "XXXXX"},
    "fail": {"id": "XXXXX"},
    "in_progress": {"id": "XXXXX"},
    "blocked": {"value": "Blocked"},
    "not_tested": {"value": "Not Tested"},
}

JIRA_TRANSITIONS = {
    "backlog": "XXX",
    "open": "XXX",
    "in_progress": "XXX",
    "resolved": "XXX",
    "closed": "XXX",
    "reopened": "XXX",
}


REPO_LAMBDA_MAP = {
    "your-backend-repo": {
        "dev": ["dev_your_lambda_function_1", "dev_your_lambda_function_2"],
        "staging": ["staging_your_lambda_function_1", "staging_your_lambda_function_2"],
        "prod": ["prod_your_lambda_function_1", "prod_your_lambda_function_2"],
    },
}


JENKINS_JOBS = {
    "your-backend-repo": {
        "e2e": "job/your-team/job/your-repo/job/e2e-tests",
        "pr_gate": "job/your-team/job/your-repo/job/pr-gate",
    },
}


JQL_TEMPLATES = {
    "ready_for_qa": (
        "project = {project} AND type in (Story, Bug, Task) "
        'AND status = "Ready for QA" '
        "ORDER BY priority DESC"
    ),
    "in_progress": (
        "project = {project} AND type in (Story, Bug, Task) "
        'AND status in ("In Progress", "In Review") '
        "ORDER BY updated DESC"
    ),
    "my_validations": (
        "project = {project} AND assignee = {username} "
        'AND status = "In QA" ORDER BY updated DESC'
    ),
}


QA_COMMENT_TEMPLATES = {
    "pass": """h3. QA Validation - PASS

*Environment:* {environment}

*Verification:*
{verification_steps}

*Test Result:* PASS - {summary}""",
    "fail": """h3. QA Validation - FAIL

*Environment:* {environment}

*Issue Found:*
{issue_description}

*Steps to Reproduce:*
{steps}

*Expected:* {expected}
*Actual:* {actual}

*Test Result:* FAIL - Returning to development for fix.""",
}


RELEASE_TESTING = {
    "template_epic": "O365-49840",
    "summary_format": "Release {version} Testing",
}
