"""Browser client for UI verification using Playwright."""

import json
import logging
import re
from typing import Any

import boto3
import jwt
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

ENV_CONFIG = {
    "integration": {
        "url": "https://integration-ui.projectraptor.io",
        "secret_id": "integration_user_auth_key",
        "user_id": "854af228-b7b1-46da-9be1-02aeb23942c7",
    },
    "qa": {
        "url": "https://qa-ui.projectraptor.io",
        "secret_id": "qa_user_auth_key",
        "user_id": "0b2387e4-9b70-4c8e-ad20-9367debafcdd",
    },
}


class BrowserClient:
    """Headless browser client for verifying UI deployments."""

    def __init__(self, region: str = "us-east-1") -> None:
        self.region = region
        self._sm_client = None

    @property
    def secrets_manager(self):
        return boto3.client("secretsmanager", region_name=self.region)

    def _generate_bypass_token(self, env: str) -> str:
        config = ENV_CONFIG.get(env)
        if not config:
            raise ValueError(f"Unknown environment: {env}. Known: {list(ENV_CONFIG.keys())}")

        secret = self.secrets_manager.get_secret_value(SecretId=config["secret_id"])
        key = json.loads(secret["SecretString"])["key"]

        now = datetime.now(tz=timezone.utc)
        claims = {
            "exp": int(now.timestamp()) + 3600,
            "jti": "aebddaf0-6e90-4c20-b262-b22913f52ac6",
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()) - 60,
            "sub": config["user_id"],
            "token_use": "access",
        }

        return jwt.encode(claims, key, algorithm="ES384")

    async def get_ui_build_info(self, env: str) -> dict[str, Any]:
        """Launch headless browser, bypass login, and capture version from console."""
        from playwright.async_api import async_playwright

        config = ENV_CONFIG.get(env)
        if not config:
            return {"status": "error", "error": f"Unknown environment: {env}"}

        token = self._generate_bypass_token(env)
        bypass_url = f"{config['url']}/login?cm_access_token={token}"

        console_messages: list[str] = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            page.on("console", lambda msg: console_messages.append(msg.text))

            try:
                await page.goto(bypass_url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(3000)
            except Exception as e:
                await browser.close()
                return {"status": "error", "error": f"Page load failed: {e}"}

            await browser.close()

        build_info = self._parse_console_output(console_messages)
        build_info["environment"] = env
        build_info["url"] = config["url"]
        build_info["console_lines"] = len(console_messages)
        return build_info

    @staticmethod
    def _parse_console_output(messages: list[str]) -> dict[str, Any]:
        result: dict[str, Any] = {"status": "success"}

        for msg in messages:
            version_match = re.search(r"Version:\s*([\d.]+)", msg)
            if version_match:
                result["version"] = version_match.group(1)

            build_match = re.search(r"Build:\s*(\S+)", msg)
            if build_match:
                result["build"] = build_match.group(1)

            env_match = re.search(r"Env:\s*(\S+)", msg)
            if env_match:
                result["reported_env"] = env_match.group(1)

        if "version" not in result:
            result["status"] = "warning"
            result["warning"] = "Version not found in console output"

        return result
