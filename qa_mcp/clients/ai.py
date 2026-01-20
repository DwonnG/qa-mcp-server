"""AI Client for Azure OpenAI integration.

This module supports OAuth-based Azure OpenAI endpoints. Configure your
OAuth credentials in AWS Secrets Manager or modify for your auth method.
"""

import base64
import json
import logging
import os
import time
from typing import Optional

import boto3
import requests
from botocore.exceptions import ClientError
from openai import AzureOpenAI

logger = logging.getLogger(__name__)


class SecretManager:
    """AWS Secrets Manager client."""

    def __init__(self, region: str = "us-east-1") -> None:
        self.client = boto3.client("secretsmanager", region_name=region)

    def get_secret_value(self, secret_id: str) -> dict | str:
        """Retrieve a secret value from AWS Secrets Manager."""
        try:
            response = self.client.get_secret_value(SecretId=secret_id)
            secret_string = response.get("SecretString")

            if not secret_string:
                logger.warning(f"SecretString is empty for secret_id: {secret_id}")
                return ""

            return json.loads(secret_string)

        except json.JSONDecodeError as e:
            logger.warning(f"SecretString is not valid JSON for {secret_id}: {e}")
            return secret_string if secret_string else ""
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            logger.error(f"AWS error for {secret_id}: {error_code} - {e}")
            return ""
        except Exception as e:
            logger.error(f"Unexpected error fetching secret {secret_id}: {e}")
            return ""

    def get_api_token(self, secret_id: str, secret_key: str) -> str:
        """Get a specific key from a secret."""
        raw = self.get_secret_value(secret_id)
        if not isinstance(raw, dict):
            raise ValueError(f"Secret '{secret_id}' was not a dict (got {type(raw)})")
        token = raw.get(secret_key)
        if not token:
            raise ValueError(f"Key '{secret_key}' not found in secret '{secret_id}'")
        return token


class AIClient:
    """Azure OpenAI client with OAuth authentication."""

    def __init__(
        self,
        secrets_manager: SecretManager,
        secret_id: str = "",
        client_id_key: str = "client_id",
        client_secret_key: str = "client_secret",
        app_key_key: str = "app_key",
    ) -> None:
        secret_id = secret_id or os.environ.get("AI_SECRET_ID", "")
        if not secret_id:
            raise ValueError("AI_SECRET_ID environment variable or secret_id parameter required")

        self.client_id = secrets_manager.get_api_token(secret_id, client_id_key)
        self.client_secret = secrets_manager.get_api_token(secret_id, client_secret_key)
        self.app_key = secrets_manager.get_api_token(secret_id, app_key_key)
        self.auth_url = os.environ.get("AI_AUTH_URL", "")
        self.azure_endpoint = os.environ.get("AI_AZURE_ENDPOINT", "")
        self.deployment_model = os.environ.get("AI_MODEL", "gpt-4")

    def get_access_token(self) -> Optional[str]:
        """Get OAuth access token."""
        try:
            creds = f"{self.client_id}:{self.client_secret}".encode("utf-8")
            basic = base64.b64encode(creds).decode("utf-8")
            headers = {
                "Accept": "*/*",
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {basic}",
            }
            resp = requests.post(
                self.auth_url,
                headers=headers,
                data="grant_type=client_credentials",
                timeout=10,
            )
            resp.raise_for_status()
            token = resp.json().get("access_token")
            if not token:
                logger.error("No access_token in OAuth response")
            return token
        except requests.RequestException as e:
            logger.error(f"Failed to fetch access token: {e}")
            return None

    def ask_openai(self, prompt: str) -> Optional[str]:
        """Send a prompt to Azure OpenAI and get a response."""
        token = self.get_access_token()
        if not token:
            return None

        client = AzureOpenAI(
            azure_endpoint=self.azure_endpoint,
            api_key=token,
            api_version="2024-07-01-preview",
        )

        retry_delay = 1
        max_retries = 5
        for attempt in range(1, max_retries + 1):
            try:
                response = client.chat.completions.create(
                    model=self.deployment_model,
                    messages=[
                        {"role": "system", "content": "You are a chatbot"},
                        {"role": "user", "content": prompt},
                    ],
                    user=f'{{"appkey": "{self.app_key}"}}',
                )
                return response.choices[0].message.content

            except Exception as e:
                logger.warning(f"Retrying OpenAI request ({attempt}/{max_retries}): {e}")
                time.sleep(retry_delay)
                retry_delay *= 2

        logger.error("Exhausted retries talking to OpenAI")
        return None
