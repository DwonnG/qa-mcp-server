#!/usr/bin/env python3
"""Entry point for QA MCP Server."""

from qa_mcp.server import mcp

if __name__ == "__main__":
    mcp.run(log_level="WARNING")
