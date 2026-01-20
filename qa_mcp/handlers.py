"""QA Analysis Handlers - AI-powered handlers for QA analysis tasks."""

import logging
from typing import Any, Dict

from .prompts import Persona, PromptBuilder

logger = logging.getLogger(__name__)


class CommentSummaryHandler:
    """Handler for comment summarization functionality."""

    def __init__(self, ai_client: Any, jira_client: Any = None) -> None:
        self.ai_client = ai_client
        self.jira_client = jira_client
        self.prompt_builder = PromptBuilder()

    def handle_comment_summary(self, request_data: Dict) -> str:
        """Handle comment summarization, fetch comments from Jira if not present."""
        try:
            ticket_key = request_data.get("ticketKey", "")
            comments = request_data.get("comments", [])

            if not comments and self.jira_client:
                issue = self.jira_client.fetch_issue_details(ticket_key)
                comments = issue.get("comments", [])

            if not comments:
                return f"No comments found for {ticket_key}"

            ticket_data = {
                "ticketKey": ticket_key,
                "comments": comments,
                "title": request_data.get("title", ""),
                "description": request_data.get("description", ""),
            }

            prompt = self.prompt_builder.build_comment_summary_prompt(ticket_data)
            logger.info(f"Generated prompt for comment summary: {ticket_key}")

            if self.ai_client:
                result = self.ai_client.ask_openai(prompt)
                if result:
                    return result

            return f"Unable to generate comment summary for {ticket_key}"

        except Exception as e:
            logger.error(f"Error generating comment summary: {e}")
            return f"Error generating comment summary for '{ticket_key}': {str(e)}"


class TestCasesHandler:
    """Handler for test case generation functionality."""

    def __init__(self, ai_client: Any) -> None:
        self.ai_client = ai_client
        self.prompt_builder = PromptBuilder()

    def handle_test_cases(self, request_data: Dict) -> str:
        """Handle test case generation."""
        try:
            ticket_key = request_data.get("ticketKey", "")

            prompt = self.prompt_builder.build_test_cases_prompt(
                ticket_data=request_data, persona=Persona.SENIOR_QA
            )

            if self.ai_client:
                result = self.ai_client.ask_openai(prompt)
                if result:
                    logger.info(f"Generated test cases for {ticket_key}")
                    return result

            return f"Unable to generate test cases for {ticket_key}"

        except Exception as e:
            logger.error(f"Error generating test cases: {e}")
            return f"Error generating test cases for '{ticket_key}': {str(e)}"


class RootCauseHandler:
    """Handler for root cause analysis functionality."""

    def __init__(self, ai_client: Any) -> None:
        self.ai_client = ai_client
        self.prompt_builder = PromptBuilder()

    def handle_root_cause(self, request_data: Dict) -> str:
        """Handle root cause analysis."""
        try:
            ticket_key = request_data.get("ticketKey", "")

            prompt = self.prompt_builder.build_root_cause_prompt(
                ticket_data=request_data, persona=Persona.TECHNICAL_LEADER
            )

            if self.ai_client:
                result = self.ai_client.ask_openai(prompt)
                if result:
                    logger.info(f"Generated root cause analysis for {ticket_key}")
                    return result

            return f"Unable to generate root cause analysis for {ticket_key}"

        except Exception as e:
            logger.error(f"Error generating root cause analysis: {e}")
            return f"Error generating root cause analysis for '{ticket_key}': {str(e)}"


class ReproductionStepsHandler:
    """Handler for reproduction steps functionality."""

    def __init__(self, ai_client: Any) -> None:
        self.ai_client = ai_client
        self.prompt_builder = PromptBuilder()

    def handle_reproduction_steps(self, request_data: Dict) -> str:
        """Handle reproduction steps generation."""
        try:
            ticket_key = request_data.get("ticketKey", "")

            prompt = self.prompt_builder.build_reproduction_steps_prompt(
                ticket_data=request_data, persona=Persona.TECHNICAL_LEADER
            )

            if self.ai_client:
                result = self.ai_client.ask_openai(prompt)
                if result:
                    logger.info(f"Generated reproduction steps for {ticket_key}")
                    return result

            return f"Unable to generate reproduction steps for {ticket_key}"

        except Exception as e:
            logger.error(f"Error generating reproduction steps: {e}")
            return f"Error generating reproduction steps for '{ticket_key}': {str(e)}"


class StoryAnalysisHandler:
    """Handler for story analysis."""

    def __init__(self, ai_client: Any, jira_client: Any) -> None:
        self.ai_client = ai_client
        self.jira_client = jira_client
        self.prompt_builder = PromptBuilder()

    def check_fix_version(self, ticket: Dict) -> tuple:
        """Check if the ticket has a valid fix version."""
        try:
            issue_details = self.jira_client.jira.issue(ticket.get("ticketKey", "N/A"))
            fix_versions = issue_details.get("fields", {}).get("fixVersions", [])
            if not fix_versions:
                return ("Missing fix version", None)
            elif len(fix_versions) > 1:
                names = [fv.get("name", "N/A") for fv in fix_versions]
                return ("Multiple fix versions", names)
            return ("Fix version is valid", fix_versions[0].get("name", ""))
        except Exception as e:
            logger.warning(f"Could not check fix version: {e}")
            return ("Could not check fix version", None)

    def handle(self, ticket_data: Dict) -> str:
        """Handle story analysis."""
        ticket_key = ticket_data.get("ticketKey", "N/A")
        title = ticket_data.get("title", "")
        description = ticket_data.get("description", "")
        team = ticket_data.get("team", "") or ticket_data.get("assignedTeam", "")
        status = ticket_data.get("status", "")
        comments = ticket_data.get("comments", [])
        issue_type = ticket_data.get("issueType", "story")

        comment_text = ""
        if comments:
            for i, comment in enumerate(comments[:3], 1):
                author = comment.get("author", "Unknown")
                content = comment.get("content", "")
                if len(content) > 200:
                    content = content[:200] + "..."
                comment_text += f"{i}. {author}: {content}\n"

        prompt = self.prompt_builder.build_story_analysis_prompt(
            persona=Persona.DEVELOPMENT_TEAM, ticket_data=ticket_data
        )

        prompt += (
            "Analyze the following Jira story and provide a structured analysis. "
            "Focus on cross-team needs, ambiguities, dependencies, risks, and follow-up questions.\n\n"
            f"**Ticket Key:** {ticket_key}\n"
            f"**Title:** {title}\n"
            f"**Type:** {issue_type}\n"
            f"**Team:** {team}\n"
            f"**Status:** {status}\n"
            f"**Description:** {description}\n\n"
            f"**Recent Comments:**\n{comment_text if comment_text else 'No recent comments.'}\n\n"
            "---\n"
            "## Story Analysis\n"
            "### 1. Cross-Team Coordination\n"
            "### 2. Ambiguities & Scope\n"
            "### 3. Dependencies & Blockers\n"
            "### 4. Risks & Issues\n"
            "### 5. Testability & Acceptance\n"
            "### 6. Follow-Up Questions\n"
        )

        check_result = self.check_fix_version(ticket_data)
        prompt += f"\n\n**Fix Version Check:** {check_result[0]}"
        if check_result[1]:
            if isinstance(check_result[1], list):
                prompt += f"\n**Fix Versions:** {', '.join(check_result[1])}"
            else:
                prompt += f"\n**Fix Version:** {check_result[1]}"

        ai_response = self.ai_client.ask_openai(prompt)
        return ai_response.strip() if ai_response else ""


class EpicAnalysisHandler:
    """Handler for epic analysis and cross-team dependencies."""

    def __init__(self, ai_client: Any, jira_client: Any) -> None:
        self.ai_client = ai_client
        self.jira_client = jira_client
        self.prompt_builder = PromptBuilder()

    def summarize_comments(self, comments: list) -> str:
        """Summarize a list of comments using AI."""
        combined_text = "\n\n".join([c.strip() for c in comments if isinstance(c, str) and c.strip()])
        if not combined_text:
            return ""

        summary_prompt = (
            "Summarize the following Jira comments into a concise overview focusing on key points, "
            "people, questions, or blockers:\n\n"
            f"{combined_text}\n\n"
            "Provide a summary that captures the essence without losing important details."
        )

        summary = self.ai_client.ask_openai(summary_prompt)
        return summary.strip() if isinstance(summary, str) else ""

    def handle_epic_analysis(self, request_data: Dict) -> str:
        """Handle epic analysis request."""
        epic_key = request_data.get("epicKey") or request_data.get("ticketKey")
        primary_team = request_data.get("primaryOwningTeam", "")
        epic_title = request_data.get("title", "")

        logger.info(f"Handling epic analysis for {epic_key}, team: {primary_team}")

        try:
            jql_query = f'"Epic Link" = {epic_key}'
            epic_issues = self.jira_client.jira.jql(jql_query).get("issues", [])

            tickets_info = []
            for issue in epic_issues[:20]:
                issue_key = issue.get("key")
                details = self.jira_client.fetch_issue_details(issue_key)
                tickets_info.append({
                    "key": issue_key,
                    "title": details.get("title", ""),
                    "status": details.get("status", ""),
                    "team": details.get("assigned_teams", ""),
                })

            tickets_text = "\n".join([
                f"- [{t['key']}] {t['title']} (Status: {t['status']}, Team: {t['team']})"
                for t in tickets_info
            ])

            prompt = (
                f"Analyze the following epic and its stories:\n\n"
                f"**Epic:** {epic_key} - {epic_title}\n"
                f"**Primary Team:** {primary_team}\n\n"
                f"**Stories:**\n{tickets_text}\n\n"
                "Provide:\n"
                "1. Cross-team dependencies (stories requiring teams other than the primary)\n"
                "2. Stories with unclear scope\n"
                "3. Dependencies and blockers\n"
                "4. Risks and issues\n"
                "5. Summary and recommendations\n"
            )

            result = self.ai_client.ask_openai(prompt)
            return result if result else f"Unable to analyze epic {epic_key}"

        except Exception as e:
            logger.error(f"Error in epic analysis: {e}")
            return f"Error analyzing epic {epic_key}: {str(e)}"
