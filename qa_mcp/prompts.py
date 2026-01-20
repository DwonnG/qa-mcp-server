"""Prompt Builder Utility - Centralized prompt management with persona-based AI interactions."""

import logging
from enum import Enum
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class Persona(Enum):
    """Available AI personas for different types of analysis."""

    SENIOR_QA = "Senior QA Technical Lead"
    SENIOR_DEV = "Senior Developer Technical Lead"
    SENIOR_PO = "Senior Product Owner"
    DEVELOPMENT_TEAM = "Senior development team"
    SCRUM_MASTER = "Senior Scrum Master"
    BUSINESS_ANALYST = "Senior Business Analyst"
    SECURITY_ENGINEER = "Senior Security Engineer"
    DEVOPS_ENGINEER = "Senior Devops Engineer"
    TECHNICAL_LEADER = "Senior Technical Lead"


class PromptBuilder:
    """Centralized prompt builder with persona-based templates."""

    def __init__(self) -> None:
        self.personas = self._define_personas()
        self.templates = self._define_templates()

    def build_story_analysis_prompt(self, ticket_data: Dict, persona: Persona) -> str:
        """Build a story analysis prompt tailored for the given persona."""
        try:
            persona_context = self.personas.get(persona, self.personas[Persona.DEVELOPMENT_TEAM])
            return f"""{persona_context['introduction']}"""
        except Exception as e:
            logger.error(f"Error building prompt: {e}")
            return self._get_fallback_prompt(ticket_data, "story_analysis")

    def build_analysis_prompt(
        self,
        ticket_data: Dict,
        analysis_type: str,
        persona: Persona = Persona.SENIOR_QA,
        context: Optional[Dict] = None,
    ) -> str:
        """Build a comprehensive analysis prompt with persona context."""
        try:
            persona_context = self.personas.get(persona, self.personas[Persona.SENIOR_QA])
            template = self.templates.get(analysis_type, self.templates["default"])
            ticket_context = self._format_ticket_context(ticket_data, context)

            prompt = f"""{persona_context['introduction']}

{template['instructions']}

{ticket_context}

{template['output_format']}

{persona_context['style_guide']}"""

            logger.info(f"Built {analysis_type} prompt with {persona.value} persona")
            return prompt

        except Exception as e:
            logger.error(f"Error building prompt: {e}")
            return self._get_fallback_prompt(ticket_data, analysis_type)

    def build_test_cases_prompt(self, ticket_data: Dict, persona: Persona = Persona.SENIOR_QA) -> str:
        """Build test case generation prompt with QA perspective."""
        return self.build_analysis_prompt(ticket_data, "test-cases", persona)

    def build_comment_summary_prompt(self, ticket_data: Dict, persona: Persona = Persona.BUSINESS_ANALYST) -> str:
        """Build comment summary prompt with Business Analyst perspective."""
        return self.build_analysis_prompt(ticket_data, "comment-summary", persona)

    def build_root_cause_prompt(self, ticket_data: Dict, persona: Persona = Persona.TECHNICAL_LEADER) -> str:
        """Build root cause analysis prompt with Technical Leader perspective."""
        return self.build_analysis_prompt(ticket_data, "root-cause-analysis", persona)

    def build_reproduction_steps_prompt(self, ticket_data: Dict, persona: Persona = Persona.TECHNICAL_LEADER) -> str:
        """Build reproduction steps prompt with Technical Leader perspective."""
        return self.build_analysis_prompt(ticket_data, "reproduction-steps", persona)

    def build_epic_analysis_prompt(self, ticket_data: Dict, persona: Persona = Persona.SENIOR_PO) -> str:
        """Build epic analysis prompt with Product Owner perspective."""
        return self.build_analysis_prompt(ticket_data, "epic-analysis", persona)

    def _define_personas(self) -> Dict[Persona, Dict[str, str]]:
        """Define AI personas with their characteristics and expertise."""
        return {
            Persona.SENIOR_QA: {
                "introduction": """You are a Senior QA Engineer with 8+ years of experience in software testing, test automation, and quality assurance. You have deep expertise in:
- Test strategy and planning
- Test case design and execution
- Risk assessment and mitigation
- Quality metrics and reporting
- Test automation frameworks
- Performance and security testing""",
                "style_guide": """Provide analysis that is:
- Thorough and methodical
- Risk-focused with mitigation strategies
- Includes specific test scenarios and cases
- Considers edge cases and boundary conditions
- Emphasizes quality gates and acceptance criteria
- Uses testing terminology and best practices""",
            },
            Persona.SENIOR_DEV: {
                "introduction": """You are a Senior Software Developer with 10+ years of experience in software architecture, design patterns, and implementation best practices.""",
                "style_guide": """Provide analysis that is technically detailed and accurate.""",
            },
            Persona.SENIOR_PO: {
                "introduction": """You are a Senior Product Owner with 7+ years of experience in product development, requirements analysis, and stakeholder communication.""",
                "style_guide": """Provide analysis that is business-value focused and user-centric.""",
            },
            Persona.DEVELOPMENT_TEAM: {
                "introduction": """You represent a cross-functional Development Team with collective expertise in development, testing, design, and delivery.""",
                "style_guide": """Provide analysis that is collaborative and team-oriented.""",
            },
            Persona.SCRUM_MASTER: {
                "introduction": """You are an experienced Scrum Master with 6+ years of experience in Agile coaching and team facilitation.""",
                "style_guide": """Provide analysis that is process and workflow focused.""",
            },
            Persona.BUSINESS_ANALYST: {
                "introduction": """You are a Senior Business Analyst with 8+ years of experience in requirements analysis and stakeholder communication.""",
                "style_guide": """Provide analysis that is process and workflow oriented.""",
            },
            Persona.TECHNICAL_LEADER: {
                "introduction": """You are a Senior Technical Lead with deep expertise in debugging, root cause analysis, and system architecture.""",
                "style_guide": """Provide analysis that is technically rigorous and actionable.""",
            },
        }

    def _define_templates(self) -> Dict[str, Dict[str, str]]:
        """Define analysis templates for different request types."""
        return {
            "test-cases": {
                "instructions": """Generate 8-12 comprehensive test cases for the ticket. Cover:

1. **Happy Path** - Main user flows and expected behavior
2. **Edge Cases** - Boundaries, empty/invalid inputs, and unusual conditions
3. **Error Handling** - Invalid actions, system errors, and fallback behavior
4. **Integration / E2E** - Cross-system workflows and complete user journeys

Each test case should be specific, verifiable, and aligned with the ticket's goals.""",
                "output_format": """Format each test case as:
**Scenario: [Title]**
- **Given:** [Setup or context]
- **When:** [Action taken]
- **Then:** [Expected outcome]
- **Priority:** [High/Medium/Low]""",
            },
            "comment-summary": {
                "instructions": """Summarize the Jira ticket comments. Extract:
- Decisions made
- Questions raised or resolved
- Blockers or dependencies
- Notable contributors""",
                "output_format": """Start with: Summary Of Comments In This Ticket
Format as a bullet list of key insights.""",
            },
            "root-cause-analysis": {
                "instructions": """Perform a Root Cause Analysis (RCA) for the bug. Structure your analysis:

**Root Cause** - What went wrong at a technical or process level
**Contributing Factors** - Conditions that enabled the issue
**Preventive Actions** - Steps to avoid recurrence""",
                "output_format": """Format using markdown:
### Jira Ticket Overview
### Root Cause
### Contributing Factors
### Preventive Actions""",
            },
            "reproduction-steps": {
                "instructions": """Write clear reproduction steps for the bug:

**Environment Details** - Where the issue occurs
**Step-by-Step Instructions** - Clear, sequential actions
**Expected vs. Actual Behavior** - What should and does happen""",
                "output_format": """Format as:
### Environment
### Steps to Reproduce
### Expected vs. Actual""",
            },
            "epic-analysis": {
                "instructions": """Analyze this epic for comprehensive planning:

1. **Epic Scope and Objectives** - Business goals and success criteria
2. **Story Breakdown Strategy** - Recommended decomposition
3. **Release Planning Approach** - MVP and phased delivery
4. **Success Metrics** - Key performance indicators""",
                "output_format": """Format as a comprehensive epic analysis with strategic recommendations.""",
            },
            "default": {
                "instructions": """Analyze this Jira ticket and provide comprehensive insights.""",
                "output_format": """Provide a structured analysis with clear sections.""",
            },
        }

    def _format_ticket_context(self, ticket_data: Dict, context: Optional[Dict] = None) -> str:
        """Format ticket information for prompt inclusion."""
        ticket_key = ticket_data.get("ticketKey", "Unknown")
        title = ticket_data.get("title", "No title provided")
        description = ticket_data.get("description", "No description available")
        issue_type = ticket_data.get("issueType", "story")
        comments = ticket_data.get("comments", [])

        formatted_context = f"""
**Ticket Information:**
- **Key:** {ticket_key}
- **Title:** {title}
- **Type:** {issue_type}
- **Description:** {description}
"""
        if comments:
            formatted_context += "\n**Recent Comments:**\n"
            for i, comment in enumerate(comments[:3], 1):
                author = comment.get("author", "Unknown")
                content = comment.get("content", "")
                if len(content) > 200:
                    content = content[:200] + "..."
                formatted_context += f"{i}. {author}: {content}\n"

        return formatted_context

    def _get_fallback_prompt(self, ticket_data: Dict, analysis_type: str) -> str:
        """Generate a simple fallback prompt when template building fails."""
        ticket_key = ticket_data.get("ticketKey", "Unknown")
        title = ticket_data.get("title", "No title")

        return f"""Analyze the following Jira ticket for {analysis_type}:

Ticket: {ticket_key}
Title: {title}
Description: {ticket_data.get('description', 'No description provided')}

Please provide a detailed {analysis_type} analysis with specific recommendations."""
