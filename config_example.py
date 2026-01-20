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


# =============================================================================
# JIRA CONFIGURATION
# =============================================================================
# Find your custom field IDs by:
# 1. Go to Jira Admin > Issues > Custom Fields
# 2. Or inspect network requests when viewing an issue

JIRA_FIELDS: JiraFieldIds = {
    "test_result": "customfield_XXXXX",  # Your "Test Result" field ID
    "validator": "customfield_XXXXX",  # Your "Validator" field ID (user picker)
    "team": "customfield_XXXXX",  # Your "Team" field ID
}

# Test Result field option values
# Find these by inspecting the field configuration or API responses
TEST_RESULT_VALUES = {
    "pass": {"id": "XXXXX"},  # Option ID for "Pass"
    "fail": {"id": "XXXXX"},  # Option ID for "Fail"
    "in_progress": {"id": "XXXXX"},  # Option ID for "In Progress"
    "blocked": {"value": "Blocked"},  # Fallback to value if ID unknown
    "not_tested": {"value": "Not Tested"},
}

# Jira workflow transition IDs
# Find by: GET /rest/api/2/issue/{issueKey}/transitions
JIRA_TRANSITIONS = {
    "backlog": "XXX",
    "open": "XXX",
    "in_progress": "XXX",
    "resolved": "XXX",
    "closed": "XXX",
    "reopened": "XXX",
    # Add your workflow-specific transitions
}


# =============================================================================
# AWS LAMBDA CONFIGURATION
# =============================================================================
# Map repositories to their Lambda function names per environment

REPO_LAMBDA_MAP = {
    "your-backend-repo": {
        "dev": [
            "dev_your_lambda_function_1",
            "dev_your_lambda_function_2",
        ],
        "staging": [
            "staging_your_lambda_function_1",
            "staging_your_lambda_function_2",
        ],
        "prod": [
            "prod_your_lambda_function_1",
            "prod_your_lambda_function_2",
        ],
    },
    # Add more repos as needed
}


# =============================================================================
# JENKINS CONFIGURATION
# =============================================================================
# Jenkins job paths (relative to JENKINS_URL)

JENKINS_JOBS = {
    "your-backend-repo": {
        "e2e": "job/your-team/job/your-repo/job/e2e-tests",
        "pr_gate": "job/your-team/job/your-repo/job/pr-gate",
    },
    # Add more repos as needed
}


# =============================================================================
# JQL TEMPLATES
# =============================================================================
# Customize JQL queries for your workflow

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


# =============================================================================
# QA COMMENT TEMPLATES
# =============================================================================
# Templates for QA validation comments

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
