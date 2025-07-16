"""Abstraction for a Zulip message."""

from dataclasses import asdict, dataclass
from typing import Any

import zulip


@dataclass(kw_only=True)
class Message:
    """Abstraction for a Zulip message."""

    type: str
    subject: str | None
    to: list[str] | str

    def to_dict(self) -> dict[str, Any]:
        """Convert the message to a dictionary."""
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Message":
        """Convert a dictionary to a message."""
        return Message(
            type=data["type"],
            subject=data.get("subject"),
            to=data["to"],
        )

    def send(self, text: str, client: zulip.Client) -> None:
        """Send the message to the client."""
        send_payload = {
            "type": self.type,
            "to": self.to,
            "subject": self.subject,
            "content": text,
        }
        client.send_message(send_payload)

    @classmethod
    def from_zulip_message(cls, message: dict, client_zulip_email: str) -> "Message":
        """Get the message from the Zulip message."""
        if message["type"] == "private":
            display_recipients = [
                user["email"]
                for user in message["display_recipient"]
                if user["email"] != client_zulip_email
            ]
            if message["sender_email"] not in display_recipients:
                display_recipients.append(message["sender_email"])
            subject = None
        else:
            display_recipients = message["display_recipient"]
            subject = message.get("subject", "arxiv")
        return cls(
            type=message["type"],
            to=display_recipients,
            subject=subject,
        )
