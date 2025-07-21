"""Kita bot for Zulip."""

import logging
import os
import re
import sqlite3
from collections import defaultdict, deque
from pathlib import Path

import openai
import zulip
from dotenv import load_dotenv

from bots.message import Message
from bots.parser import parse_zulip_message

load_dotenv()

logger = logging.getLogger(__name__)


class Kita:
    """Kita bot for Zulip."""

    doc = """
Know IT All (Kita) can help resolve conflicts and answer questions using OpenAI's GPT!

Usage:
  @**kita** --help
  @**kita** --reset
  @**kita** --tokens
  @**kita** --users
  @**kita** --reset-tokens <user_id>
  @**kita** --model
  @**kita** <prompt>...

Commands:
  --reset         Reset the memory for this conversation.
  --tokens        Show your total token usage.
  --users         List all users and their IDs.
  --reset-tokens  Reset token usage for the given user ID.
  --model         See the OpenAI model used.

Arguments:
  <prompt>...   The prompt to send to the model.
  <user_id>     The user ID to reset token usage for.
"""

    def __init__(self):
        """Initialize the Kita bot."""
        self.admin_id = int(os.getenv("ZULIP_ADMIN_ID", "000000"))
        self.max_tokens = 1_000_000
        self.db_file = Path(os.getenv("KITA_DB_FILE", "data/kita.db"))
        self.model = os.getenv("KITA_MODEL", "o4-mini")

        self.client_ai = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.client_zulip = zulip.Client(config_file=".zuliprc/kita")

        self.conversation_memory = defaultdict(lambda: deque(maxlen=10))
        self.token_usage = defaultdict(int)

        self.setup_db()
        self.load_token_usage()

        self.parse = lambda x: parse_zulip_message(x, self.doc)

    def run(self):
        """Run the Kita bot."""
        self.client_zulip.call_on_each_event(self.handle_event, event_types=["message"])

    def setup_db(self):
        """Set up the database."""
        self.db_file.parent.mkdir(parents=True, exist_ok=True)
        self.db_file.touch(exist_ok=True)
        with sqlite3.connect(self.db_file) as conn:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS token_usage (
                    user_id INTEGER PRIMARY KEY,
                    tokens INTEGER DEFAULT 0
                )
            """)
            conn.commit()

    def save_token_usage(self):
        """Save token usage to the database."""
        with sqlite3.connect(self.db_file) as conn:
            c = conn.cursor()
            for user_id, tokens in self.token_usage.items():
                q = "INSERT OR REPLACE INTO token_usage (user_id, tokens) VALUES (?, ?)"
                c.execute(
                    q,
                    (user_id, tokens),
                )
            conn.commit()

    def load_token_usage(self):
        """Load token usage from the database."""
        self.token_usage = defaultdict(int)
        with sqlite3.connect(self.db_file) as conn:
            c = conn.cursor()
            for row in c.execute("SELECT user_id, tokens FROM token_usage"):
                self.token_usage[row[0]] = row[1]

    def reset_tokens_for_user(self, sender_id: int, content: str) -> str:
        """Reset token usage for a user."""
        if sender_id != self.admin_id:
            return "🚫 You are not authorized to use this command."

        match = re.match(
            r"^@\*\*kita\*\*\s*--reset-tokens\s+(\S+)", content.strip(), re.IGNORECASE
        )
        if not match:
            return "❓ Usage: @**kita** --reset-tokens user_id"

        user_id = match.group(1)

        if user_id.isdigit():
            user_id = int(user_id)
        else:
            return "❓ Usage: @**kita** --reset-tokens user_id"

        if user_id not in self.token_usage:
            return f"❓ No user with token usage found with user ID {user_id}."

        self.token_usage[user_id] = 0
        self.save_token_usage()
        return f"✅ Token usage reset for user ID {user_id}."

    def get_all_users(self) -> str:
        """Get all users and their IDs."""
        response = self.client_zulip.get_users()

        reply = [
            "**👥 List of all users:**",
            "",
        ]
        for user in response["members"]:
            reply.extend(
                [f"- `{user['user_id']}` | {user['full_name']} | `{user['email']}`"]
            )
        return "\n".join(reply)

    def get_conversation_id(
        self, message: dict
    ) -> tuple[str, str] | tuple[str, ...] | None:
        """Identify a conversation.

        - For streams: (stream_name, topic)
        - For PMs: tuple of all participant IDs (sorted, order-independent).
        """
        if message["type"] == "private":
            # For PMs, display_recipient is a list of user dicts (with "id" keys)
            user_ids = sorted(user["id"] for user in message["display_recipient"])
            return tuple(user_ids)
        if message["type"] == "stream":
            # For streams, display_recipient is the stream name (str) and subject is
            # the topic name of the stream
            return (message["display_recipient"], message["subject"])
        return None

    def handle_message_to_openai(
        self,
        *,
        sender: int,
        content: str,
        conv_id: tuple[str, str] | tuple[str, ...] | None,
        reply: Message,
    ) -> None:
        """Handle a message to OpenAI."""
        if self.token_usage[sender] > self.max_tokens:
            reply.send(
                "🚫 You have reached the maximum token usage for this month."
                "You can ask Georgios Arampatzis to reset your token usage.",
                self.client_zulip,
            )
            return

        if content.startswith("@**kita**"):
            content = content[len("@**kita**") :].strip()

        # Add new user message to memory
        self.conversation_memory[conv_id].append({"role": "user", "content": content})
        # Prepare message history for OpenAI
        messages = list(self.conversation_memory[conv_id])

        logger.info("messages being sent to OpenAI: %s", messages)

        try:
            response = self.client_ai.chat.completions.create(
                model=self.model,
                messages=messages,
                max_completion_tokens=1000,
            )

            logger.info("Raw OpenAI response: %s", response)

            choice = response.choices[0]
            ai_response = getattr(getattr(choice, "message", None), "content", None)
            if ai_response:
                ai_response = ai_response.strip()
            else:
                raise ValueError("No content returned in response from AI model.")  # noqa: TRY301

            if not ai_response:
                raise ValueError("No content returned in response from AI model.")  # noqa: TRY301

            # Add reply message to memory
            if ai_response:  # Only store non-empty replies
                self.conversation_memory[conv_id].append(
                    {
                        "role": "assistant",
                        "content": ai_response,
                    }
                )

            # Count tokens
            usage = getattr(response, "usage", None)
            if usage and hasattr(usage, "total_tokens"):
                self.token_usage[sender] += usage.total_tokens
                self.save_token_usage()

            reply.send(ai_response, self.client_zulip)

        except Exception:
            logger.exception("Error calling OpenAI API")
            reply.send(
                "Error calling OpenAI API. Please try again later.",
                self.client_zulip,
            )

    def handle_event(self, event):
        """Handle a Zulip event."""
        message = event["message"]
        content = message["content"].strip()
        sender = message["sender_id"]
        reply = Message.from_zulip_message(message, self.client_zulip.email)

        if message["sender_email"] == self.client_zulip.email:
                return

        if event["sender_type"] == "bot":
            reply.send(
                "This bot does not respond to other bots.",
                self.client_zulip
            )
            logger.info("Skipping bot message: %s", event)
            return

        conv_id = self.get_conversation_id(message)

        cmd_args = self.parse(content)

        if cmd_args is None:
            reply.send(
                "Unknown or malformed command. Use `@**kita** --help` for usage.",
                self.client_zulip,
            )
            return
        
        

        if cmd_args.get("help"):
            reply.send(f"```text\n{cmd_args['help_message']}\n```", self.client_zulip)

        elif cmd_args.get("--reset"):
            self.conversation_memory[conv_id].clear()
            reply.send("💡 Memory reset for this conversation.", self.client_zulip)

        elif cmd_args.get("--tokens"):
            reply.send(
                f"💸 Total tokens used by you: {self.token_usage[sender]}\n",
                self.client_zulip,
            )

        elif cmd_args.get("--users"):
            reply.send(self.get_all_users(), self.client_zulip)

        elif cmd_args.get("--reset-tokens"):
            reply.send(self.reset_tokens_for_user(sender, content), self.client_zulip)

        elif cmd_args.get("--model"):
            reply.send(f"🤖 GPT model: {self.model}\n", self.client_zulip)

        else:
            self.handle_message_to_openai(
                sender=sender,
                content=content,
                conv_id=conv_id,
                reply=reply,
            )
