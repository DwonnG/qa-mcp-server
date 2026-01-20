"""Webex client for reading messages and posting updates."""

import os
from typing import Any

import httpx


class WebexClient:
    """Client for interacting with Webex API."""

    def __init__(self) -> None:
        self.base_url = "https://webexapis.com/v1"
        self.token = os.getenv("WEBEX_TOKEN", "")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def list_rooms(self, max_rooms: int = 50) -> dict[str, Any]:
        """List all rooms/spaces the bot has access to."""
        client = await self._get_client()
        try:
            response = await client.get(
                "/rooms",
                params={"max": max_rooms, "sortBy": "lastactivity"},
            )
            response.raise_for_status()
            data = response.json()

            rooms = [
                {
                    "id": room["id"],
                    "title": room["title"],
                    "type": room["type"],
                    "last_activity": room.get("lastActivity"),
                    "created": room.get("created"),
                }
                for room in data.get("items", [])
            ]
            return {"status": "success", "count": len(rooms), "rooms": rooms}
        except httpx.HTTPError as e:
            return {"status": "error", "error": str(e)}

    async def get_room_by_title(self, title: str) -> dict[str, Any] | None:
        """Find a room by its title (partial match)."""
        rooms_result = await self.list_rooms(max_rooms=100)
        if rooms_result["status"] != "success":
            return None

        title_lower = title.lower()
        for room in rooms_result["rooms"]:
            if title_lower in room["title"].lower():
                return room
        return None

    async def get_messages(self, room_id: str, max_messages: int = 50) -> dict[str, Any]:
        """Get recent messages from a room."""
        client = await self._get_client()
        try:
            response = await client.get(
                "/messages",
                params={"roomId": room_id, "max": max_messages},
            )
            response.raise_for_status()
            data = response.json()

            messages = [
                {
                    "id": msg["id"],
                    "person_email": msg.get("personEmail", "unknown"),
                    "text": msg.get("text", ""),
                    "created": msg.get("created"),
                    "has_files": bool(msg.get("files")),
                }
                for msg in data.get("items", [])
            ]
            messages.reverse()
            return {"status": "success", "room_id": room_id, "count": len(messages), "messages": messages}
        except httpx.HTTPError as e:
            return {"status": "error", "error": str(e)}

    async def post_message(self, room_id: str, text: str, markdown: str | None = None) -> dict[str, Any]:
        """Post a message to a room."""
        client = await self._get_client()
        payload: dict[str, str] = {"roomId": room_id}
        if markdown:
            payload["markdown"] = markdown
        else:
            payload["text"] = text

        try:
            response = await client.post("/messages", json=payload)
            response.raise_for_status()
            data = response.json()
            return {
                "status": "success",
                "message_id": data["id"],
                "room_id": data["roomId"],
                "created": data["created"],
            }
        except httpx.HTTPError as e:
            return {"status": "error", "error": str(e)}

    async def search_messages(self, room_id: str, search_term: str, max_messages: int = 100) -> dict[str, Any]:
        """Search for messages containing a term in a room."""
        messages_result = await self.get_messages(room_id, max_messages)
        if messages_result["status"] != "success":
            return messages_result

        search_lower = search_term.lower()
        matching = [msg for msg in messages_result["messages"] if search_lower in msg["text"].lower()]
        return {
            "status": "success",
            "room_id": room_id,
            "search_term": search_term,
            "count": len(matching),
            "messages": matching,
        }

    async def get_room_summary(self, room_id: str, max_messages: int = 30) -> dict[str, Any]:
        """Get messages formatted for AI summarization."""
        messages_result = await self.get_messages(room_id, max_messages)
        if messages_result["status"] != "success":
            return messages_result

        formatted = []
        for msg in messages_result["messages"]:
            sender = msg["person_email"].split("@")[0]
            text = msg["text"]
            if text:
                formatted.append(f"[{sender}]: {text}")

        return {
            "status": "success",
            "room_id": room_id,
            "message_count": len(formatted),
            "conversation": "\n".join(formatted),
        }

    async def get_my_info(self) -> dict[str, Any]:
        """Get info about the authenticated user/bot."""
        client = await self._get_client()
        try:
            response = await client.get("/people/me")
            response.raise_for_status()
            data = response.json()
            return {
                "status": "success",
                "id": data["id"],
                "display_name": data["displayName"],
                "emails": data.get("emails", []),
                "type": data.get("type", "unknown"),
            }
        except httpx.HTTPError as e:
            return {"status": "error", "error": str(e)}
