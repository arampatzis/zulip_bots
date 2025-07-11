import re
import sqlite3
import zulip
import openai
import os
from pathlib import Path
from dotenv import load_dotenv
from collections import defaultdict, deque

load_dotenv()


class Kita:
    help_text = """
:robot: **Kita Bot Help**

Know IT All (Kita) can help resolve conflicts and answer questions using OpenAI's GPT!

**Features:**
- Remembers up to **10 messages** per conversation.
- Each user gets **1 million tokens/month** (~4 characters/token).

**Commands:**
- `@**kita** --help`
  *Show this help message.*
- `@**kita** --reset`
  *Reset the memory for this conversation.*
- `@**kita** --tokens`
  *Show your total token usage.*
- `@**kita** --users`
  *List all users and their IDs.*
- `@**kita** --reset-tokens user_id`
  *Admin: Reset token usage for the given user ID.*

Just mention `@**kita**` in your message to chat as normal!

*Bot admin: Only you can use certain management commands.*
"""

    admin_id = int(os.getenv("KITA_ADMIN_ID", "000000"))

    max_tokens = 1_000_000

    db_file = Path("data/kita_state.db")

    model = "o4-mini"

    def __init__(self):
        self.client_ai = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.client_zulip = zulip.Client(config_file="kita.zuliprc")

        self.conversation_memory = defaultdict(lambda: deque(maxlen=10))
        self.token_usage = defaultdict(int)

        self.setup_db()
        self.load_token_usage()

    def run(self):
        self.client_zulip.call_on_each_event(self.handle_event, event_types=["message"])

    def setup_db(self):
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
        with sqlite3.connect(self.db_file) as conn:
            c = conn.cursor()
            for user_id, tokens in self.token_usage.items():
                c.execute(
                    "INSERT OR REPLACE INTO token_usage (user_id, tokens) VALUES (?, ?)",
                    (user_id, tokens),
                )
            conn.commit()

    def load_token_usage(self):
        self.token_usage = defaultdict(int)
        with sqlite3.connect(self.db_file) as conn:
            c = conn.cursor()
            for row in c.execute("SELECT user_id, tokens FROM token_usage"):
                self.token_usage[row[0]] = row[1]

    def reset_tokens_for_user(self, sender_id: int, content: str) -> str:
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
        # Fetch all users
        response = self.client_zulip.get_users()

        reply = [
            "**👥 List of all users:**",
            "",
        ]
        for user in response["members"]:
            reply.append(
                f"- `{user['user_id']}` | {user['full_name']} | `{user['email']}`"
            )
        return "\n".join(reply)

    def get_conversation_id(
        self, message: dict
    ) -> tuple[str, str] | tuple[str, ...] | None:
        """
        Identify a conversation:
        - For streams: (stream_name, topic)
        - For PMs: tuple of all participant IDs (sorted, order-independent)
        """
        if message["type"] == "private":
            # For PMs, display_recipient is a list of user dicts (with "id" keys)
            user_ids = sorted(user["id"] for user in message["display_recipient"])
            return tuple(user_ids)
        elif message["type"] == "stream":
            # For streams, display_recipient is the stream name (str) and subject is
            # the topic name of the stream
            return (message["display_recipient"], message["subject"])
        else:
            return None

    def handle_event(self, event):
        message = event["message"]
        content = message["content"].strip()
        sender = message["sender_id"]
        conv_id = self.get_conversation_id(message)

        if message["sender_email"] == self.client_zulip.email:
            return

        if self.token_usage[sender] > self.max_tokens:
            reply = (
                "🚫 You have reached the maximum token usage for this month."
                "You can ask Georgios Arampatzis to reset your token usage."
            )

        elif re.match(
            r"^@\*\*kita\*\*\s*--reset-hisory", content.strip(), re.IGNORECASE
        ):
            self.conversation_memory[conv_id].clear()
            reply = "💡 Memory reset for this conversation."

        elif re.match(r"^@\*\*kita\*\*\s*--model", content.strip(), re.IGNORECASE):
            reply = f" ⚙️ GPT model: {self.model}\n"

        elif re.match(r"^@\*\*kita\*\*\s*--tokens", content.strip(), re.IGNORECASE):
            reply = f"💸 Total tokens used by you: {self.token_usage[sender]}\n"

        elif re.match(
            r"^@\*\*kita\*\*\s*--reset-tokens\s+(\S+)", content.strip(), re.IGNORECASE
        ):
            reply = self.reset_tokens_for_user(sender, content)

        elif re.match(r"^@\*\*kita\*\*\s*--users", content.strip(), re.IGNORECASE):
            reply = self.get_all_users()

        elif re.match(r"^@\*\*kita\*\*\s*--help", content.strip(), re.IGNORECASE):
            reply = self.help_text

        else:
            # Add new user message to memory
            self.conversation_memory[conv_id].append(
                {"role": "user", "content": content}
            )
            # Prepare message history for OpenAI
            messages = list(self.conversation_memory[conv_id])

            print("DEBUG - messages being sent to OpenAI:", messages)

            try:
                response = self.client_ai.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_completion_tokens=1000,
                )

                print("DEBUG - RAW OPENAI RESPONSE:", response)

                choice = response.choices[0]
                reply = getattr(getattr(choice, "message", None), "content", None)
                if reply:
                    reply = reply.strip()
                else:
                    raise ValueError("No content returned in response from AI model.")

                if not reply:
                    raise ValueError("No content returned in response from AI model.")

                # Add reply message to memory
                if reply:  # Only store non-empty replies
                    self.conversation_memory[conv_id].append(
                        {
                            "role": "assistant",
                            "content": reply,
                        }
                    )

                # Count tokens
                usage = getattr(response, "usage", None)
                if usage and hasattr(usage, "total_tokens"):
                    self.token_usage[sender] += usage.total_tokens
                    self.save_token_usage()

                    print(reply)

            except Exception as e:
                reply = f"Error calling ChatGPT: {e}"

        if message["type"] == "private":
            # display_recipient is a list of user dicts; extract emails or user_ids
            recipients = [
                user["email"]
                for user in message["display_recipient"]
                if user["email"] != self.client_zulip.email
            ]
            # Optionally, also add sender (if bot is not always in recipient list)
            if message["sender_email"] not in recipients:
                recipients.append(message["sender_email"])
            send_payload = {
                "type": "private",
                "to": recipients,
                "content": reply,
            }
        else:
            send_payload = {
                "type": "stream",
                "to": message["display_recipient"],  # stream name
                "subject": message.get("subject", ""),
                "content": reply,
            }

        self.client_zulip.send_message(send_payload)


def main():
    print("ChatGPT Bot started with memory and token tracking!")

    kita = Kita()

    try:
        kita.run()
    except KeyboardInterrupt:
        print("\nBot stopped by user (KeyboardInterrupt). Exiting gracefully.")


if __name__ == "__main__":
    main()
