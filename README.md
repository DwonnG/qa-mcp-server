# QA MCP Server

An AI-powered QA automation server built on the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/). Integrates Jira, GitHub, Jenkins, AWS, and Webex into a unified interface for QA engineers.

![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## Features

### Jira Integration
- Find tickets ready for QA or in progress
- Claim tickets for validation (assign + set validator + update status)
- Mark tickets as passed/failed with formatted comments
- Generate AI-powered test cases from ticket descriptions
- Summarize comment threads
- Analyze stories and epics for QA readiness

### GitHub Integration
- Find PRs linked to Jira tickets
- Check PR merge status and commit details
- Verify code changes before testing

### Jenkins Integration
- Check E2E test results
- Trigger builds with custom parameters
- Monitor build history
- Wait for builds and update PR descriptions with results

### AWS Integration
- Verify Lambda deployments via last-modified timestamps
- Compare deployments across environments
- Confirm code is deployed before testing

### Webex Integration
- List and read messages from Webex rooms
- Search for discussions about specific topics
- Post updates and notifications
- AI-powered conversation summaries

## Quick Start

### Prerequisites

- Python 3.11+
- Docker (recommended) or local Python environment
- API tokens for the services you want to use

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/qa-mcp-server.git
   cd qa-mcp-server
   ```

2. **Copy and configure settings**
   ```bash
   cp config_example.py config.py
   cp examples/env.example .env
   # Edit config.py with your Jira field IDs, Jenkins paths, JQL templates, etc.
   # Edit .env with your API tokens
   ```
   
   > **Important:** Your `config.py` must be mounted into the Docker container (see step 4) for custom settings to take effect.

3. **Build the Docker image**
   ```bash
   docker build -t qa-mcp-server .
   ```

4. **Add to your MCP client** (e.g., Cursor, Claude Desktop)
   
   Add to your MCP configuration (e.g., `~/.cursor/mcp.json`).
   
   > **Note:** The `config.py` volume mount is required for custom JQL templates, field mappings, and Jenkins job paths to work. Update the path to match your local installation.
   ```json
   {
     "mcpServers": {
       "qa-automation": {
         "command": "docker",
         "args": [
           "run", "-i", "--rm",
           "-e", "JIRA_URL=https://your-jira.atlassian.net",
           "-e", "JIRA_PERSONAL_TOKEN=your_token",
           "-e", "GITHUB_HOST=https://api.github.com",
           "-e", "GITHUB_TOKEN=ghp_your_token",
           "-e", "JENKINS_URL=https://your-jenkins.com",
           "-e", "JENKINS_USER=your_user",
           "-e", "JENKINS_TOKEN=your_token",
           "-e", "AWS_REGION=us-east-1",
           "-e", "WEBEX_TOKEN=your_webex_token",
           "-v", "/path/to/.aws:/root/.aws:ro",
           "-v", "/path/to/qa-mcp-server/config.py:/app/config.py:ro",
           "qa-mcp-server:latest"
         ]
       }
     }
   }
   ```

### Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Run the server
python run.py
```

## Configuration

### config.py

This file contains organization-specific settings:

| Setting | Description |
|---------|-------------|
| `JIRA_FIELDS` | Custom field IDs for your Jira instance |
| `JIRA_TRANSITIONS` | Workflow transition IDs |
| `REPO_LAMBDA_MAP` | Maps repos to Lambda function names |
| `JENKINS_JOBS` | Jenkins job paths |
| `JQL_TEMPLATES` | JQL query templates |

See `config_example.py` for a template with documentation.

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `JIRA_URL` | Yes | Your Jira instance URL |
| `JIRA_PERSONAL_TOKEN` | Yes | Jira API token or PAT |
| `JIRA_VERIFY_SSL` | No | Set to `false` for self-signed certs |
| `GITHUB_HOST` | No | GitHub API URL (default: api.github.com) |
| `GITHUB_TOKEN` | Yes | GitHub personal access token |
| `JENKINS_URL` | Yes* | Jenkins server URL |
| `JENKINS_USER` | Yes* | Jenkins username |
| `JENKINS_TOKEN` | Yes* | Jenkins API token |
| `AWS_REGION` | No | AWS region (default: us-east-1) |
| `WEBEX_TOKEN` | No | Webex bot or personal token |

*Required only if using Jenkins features

## Available Tools

### Jira Tools
- `qa_find_in_progress` - Find tickets developers are working on
- `qa_claim_ticket` - Claim a ticket for QA validation
- `qa_resolve_pass` - Mark ticket as QA passed
- `qa_fail_ticket` - Mark ticket as QA failed with bug report
- `qa_add_comment` - Add a comment to any ticket
- `qa_generate_test_cases` - AI-generated test cases
- `qa_summarize_comments` - Summarize ticket comments
- `qa_analyze_story` - Analyze story for QA readiness
- `qa_analyze_epic` - Analyze epic for release readiness

### GitHub Tools
- `qa_get_pr_info` - Get PR details
- `qa_find_prs_for_ticket` - Find PRs linked to a Jira ticket
- `qa_find_pr_for_commit` - Find PR that introduced a commit

### Jenkins Tools
- `qa_check_e2e_tests` - Check E2E test results
- `qa_get_recent_builds` - Get build history
- `qa_trigger_e2e_tests` - Trigger a test build
- `qa_get_my_test_builds` - View your Jenkins test builds
- `qa_wait_for_build_and_update_pr` - Wait for build and update PR

### AWS Tools
- `qa_check_deployment` - Verify Lambda deployment
- `qa_check_all_deployments` - Check all Lambdas for a repo
- `qa_compare_environments` - Compare deployments across envs
- `qa_get_deployment_summary` - Formatted deployment status

### Webex Tools
- `webex_list_rooms` - List accessible Webex rooms
- `webex_get_messages` - Read messages from a room
- `webex_summarize_room` - AI summary of conversation
- `webex_post_message` - Post a message
- `webex_search_messages` - Search for messages

### Workflow Tools
- `qa_get_ticket_context` - Full context (Jira + PRs + deployment)
- `qa_verify_and_resolve_vulnerability` - One-click vuln verification

## Example Usage

```
You: "Are there any tickets ready for QA?"
AI: Found 3 tickets in QA status...

You: "Claim PROJ-12345 for QA"
AI: Claimed! Assigned to you, validator set, status updated to In Progress.

You: "Check if the PR for PROJ-12345 is merged and deployed"
AI: PR #456 merged 2 hours ago. Lambda last modified 1 hour ago. Deployed!

You: "Mark PROJ-12345 as passed - verified login flow works correctly"
AI: Resolved as passed with QA comment added.
```

## Project Structure

```
qa-mcp-server/
├── run.py                    # Entry point
├── config.py                 # Your settings (git-ignored)
├── config_example.py         # Settings template
├── requirements.txt          # Dependencies
├── Dockerfile               
├── README.md
├── LICENSE
│
├── qa_mcp/                   # Main package
│   ├── __init__.py
│   ├── server.py             # MCP server with all tools
│   ├── handlers.py           # AI analysis handlers
│   ├── prompts.py            # AI prompt templates
│   │
│   └── clients/              # Service integrations
│       ├── __init__.py
│       ├── jira.py
│       ├── github.py
│       ├── jenkins.py
│       ├── aws.py
│       ├── webex.py
│       └── ai.py
│
└── examples/                 # Configuration examples
    ├── env.example           # Environment variables template
    └── mcp_config.json       # MCP client config example
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      MCP Client                              │
│                 (Cursor, Claude Desktop)                     │
└─────────────────────────┬───────────────────────────────────┘
                          │ MCP Protocol
┌─────────────────────────▼───────────────────────────────────┐
│                    QA MCP Server                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │  Jira    │  │  GitHub  │  │ Jenkins  │  │   AWS    │    │
│  │  Client  │  │  Client  │  │  Client  │  │  Client  │    │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘    │
│       │             │             │             │           │
│  ┌────▼─────────────▼─────────────▼─────────────▼────┐     │
│  │                   config.py                        │     │
│  │         (Organization-specific settings)           │     │
│  └────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

## Roadmap

**v1.1 - Modular Integrations**
- [ ] Feature flags to enable/disable integrations (Webex, Jenkins, AWS)
- [ ] Only register MCP tools for configured services
- [ ] Graceful handling when optional services aren't configured

**v1.2 - Flexible Jira Support**
- [ ] Make custom fields (validator, test_result) optional
- [ ] Support Jira Cloud and Jira Server/Data Center
- [ ] Configurable workflow transitions (not hardcoded IDs)

**v1.3 - CI/CD Abstraction**
- [ ] Abstract CI/CD interface (not just Jenkins)
- [ ] GitHub Actions support
- [ ] GitLab CI support

**v1.4 - Deployment Verification**
- [ ] Abstract deployment checker (not just AWS Lambda)
- [ ] Kubernetes deployment status
- [ ] Generic health check endpoints

**v1.5 - Testing & Quality**
- [ ] Unit tests for clients
- [ ] Integration test examples
- [ ] CI pipeline for the project itself

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built with [FastMCP](https://github.com/jlowin/fastmcp)
- Inspired by the need to automate repetitive QA tasks
- Thanks to the MCP community for the protocol specification