"""Arxiv bot for Zulip.

The bot is used to manage arxiv queries.

It can be used to add new queries, list existing queries, remove queries,
and force update on a query.

It can also be used to send updates to all queries at a given time.

The bot is configured to send updates at 7am UTC every day.
"""

import atexit
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import arxiv
import openai
import zulip
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from ratelimit import limits, sleep_and_retry

from bots.arxiv.requests import Request, RequestList
from bots.message import Message
from bots.parser import parse_zulip_message

load_dotenv()

logger = logging.getLogger(__name__)


class Arxiv:
    """Arxiv bot for Zulip."""

    admin_id = int(os.getenv("ZULIP_ADMIN_ID", "0"))

    db_file = Path(os.getenv("ARXIV_DB_FILE", "data/arxiv.db"))

    doc = """
A bot to manage arxiv queries.

Usage:
  @**arxiv** --help
  @**arxiv** set <query>...
  @**arxiv** list [all]
  @**arxiv** rm <query_id>
  @**arxiv** force <query_id>

Commands:
  set           Add a new arxiv query.
  list          List your queries, or all queries if 'all' is given.
  rm            Remove a saved query by its ID.
  force         Force update on a query by its ID.
  help          Show this help.

Arguments:
  <query>       Query to add (can be multiple tokens, e.g. cat:cs.LG AND all:GAN).
  <query_id>    ID of the query.

Examples:
  @**arxiv** --help
  @**arxiv** set cat:cs.LG AND all:GAN AND submittedDate:[20220101 TO 20231231]
  @**arxiv** rm 123456
  @**arxiv** list
  @**arxiv** list all
  @**arxiv** force 123456
"""

    def __init__(self) -> None:
        """Initialize the Arxiv bot."""
        self.requests = RequestList.load_from_file(self.db_file)
        self.scheduler = BackgroundScheduler()
        self.scheduler.add_job(
            self.send_updates_to_all_requests,
            "cron",
            hour=7,
            minute=0,
            id="arxiv-daily-update",
        )
        self.client_ai = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.client_zulip = zulip.Client(config_file=".zuliprc/arxiv")

        atexit.register(self.exit_handler)

        self.parse = lambda x: parse_zulip_message(x, self.doc)

    def exit_handler(self):
        """Save the requests to the database and shutdown the scheduler."""
        self.requests.save_to_file(self.db_file)
        self.scheduler.shutdown()

    # arxiv API: 1 request per 3 seconds
    @sleep_and_retry
    @limits(calls=1, period=3)
    def send_updates_to_single_request(self, request_id: str) -> None:
        """Send arXiv search results for the specified request id."""
        request = self.requests.get(request_id)
        if not request:
            logger.warning("Request ID %s not found.", request_id)
            return
        try:
            search = arxiv.Search(
                query=request.query,
                max_results=10,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending,
            )
            text_lines = []

            # Compute 7am yesterday (UTC)
            now = datetime.now(UTC)
            yesterday_7am = (now - timedelta(days=1)).replace(
                hour=7, minute=0, second=0, microsecond=0
            )

            for result in search.results():
                if result.published > yesterday_7am:
                    text_lines.append(f"- [{result.title}]({result.entry_id})")
                else:
                    break  # Results are sorted, stop when older than threshold

            text = "\n".join(text_lines) if text_lines else "No new results found."
            request.message.send(text, self.client_zulip)

        except Exception:
            logger.exception("arXiv fetch/send failed")

    def send_updates_to_all_requests(self) -> None:
        """Send updates to all registered requests."""
        for request_id in self.requests.ids():
            self.send_updates_to_single_request(request_id)

    def run(self) -> None:
        """Start listening for Zulip messages."""
        self.scheduler.start()
        self.client_zulip.call_on_each_event(
            self.handle_event,
            event_types=["message"],
            callback_data=self.client_zulip.email,
        )

    def get_request_id_from_zulip_message(self, message: dict) -> tuple[str, ...]:
        """Identify a conversation.

        - For streams: (stream_name, topic)
        - For PMs: tuple of all participant IDs (sorted).
        """
        if message["type"] == "private":
            user_ids = sorted(str(user["id"]) for user in message["display_recipient"])
            return tuple(user_ids)
        if message["type"] == "stream":
            return (str(message["display_recipient"]), str(message["subject"]))
        raise ValueError(f"Unknown message type: {message['type']}")

    def _set_command(
        self,
        query: str,
        message: dict,
        reply: Message,
        sender_id: int,
    ) -> None:
        """Add a new request to the database."""
        new_request = Request(
            id=self.get_request_id_from_zulip_message(message),
            query=query,
            owner_id=sender_id,
            message=reply,
        )
        if self.requests.add(new_request):
            self.requests.save_to_file(self.db_file)
            reply.send(
                f"✅ Search topic added!\nID: `{new_request.uuid}`",
                self.client_zulip,
            )
        else:
            reply.send("This search topic already exists.", self.client_zulip)

    def _rm_command(
        self,
        request_id: str,
        reply: Message,
        sender_id: int,
    ) -> None:
        """Remove a request from the database."""
        request = self.requests.get(request_id)

        print(request_id)
        print(request)

        if not request:
            reply.send("No such request ID.", self.client_zulip)
            return
        if sender_id not in (request.owner_id, self.admin_id):
            reply.send(
                "You don't have permission to remove this topic.",
                self.client_zulip,
            )
            return
        self.requests.remove(request_id)
        self.requests.save_to_file(self.db_file)
        reply.send("✅ Search topic removed!", self.client_zulip)

    def _list_command(
        self,
        scope: str,
        reply: Message,
        sender_id: int,
    ) -> None:
        """List the requests in the database."""
        show_all = scope == "all"
        msg = "🔎 All search topics:\n" if show_all else "🔎 Your search topics:\n"
        found = False
        for request in self.requests:
            if show_all or request.owner_id == sender_id:
                found = True
                msg += (
                    f"- [`{request.uuid}`] (owner: {request.owner_id})\n"
                    f"    query: `{request.query}`\n"
                )
        if not found:
            msg += "None."
        reply.send(msg, self.client_zulip)

    def _force_command(
        self,
        request_id: str,
        reply: Message,
    ) -> None:
        """Force update on a request."""
        if not self.requests.get(request_id):
            reply.send(f"Request ID `{request_id}` not found.", self.client_zulip)
            return
        self.send_updates_to_single_request(request_id)

    def handle_event(self, event: dict) -> None:
        """Handle Zulip events."""
        try:
            message = event["message"]
            content = message["content"]
            sender_id = message["sender_id"]
            reply = Message.from_zulip_message(message, self.client_zulip.email)
            if (
                event.get("type") != "message"
                or message["sender_email"] == self.client_zulip.email
            ):
                return

            cmd_args = self.parse(content)
            logger.info("cmd_args: %s", cmd_args)

            if cmd_args is None:
                reply.send(
                    "Unknown or malformed command. Use `@**arxiv** --help` for usage.",
                    self.client_zulip,
                )
                return

            # Map docopt dict keys to your actions:
            if cmd_args.get("help"):
                reply.send(
                    f"```text\n{cmd_args['help_message']}\n```", self.client_zulip
                )

            elif cmd_args.get("set"):
                query = " ".join(cmd_args["<query>"])
                self._set_command(query, message, reply, sender_id)

            elif cmd_args.get("rm"):
                self._rm_command(cmd_args["<query_id>"], reply, sender_id)

            elif cmd_args.get("list"):
                self._list_command(
                    cmd_args["all"] if cmd_args["all"] else "", reply, sender_id
                )

            elif cmd_args.get("force"):
                self._force_command(cmd_args["<query_id>"], reply)

            else:
                reply.send(
                    "Unknown command. Use `@**arxiv** --help` for help.",
                    self.client_zulip,
                )

        except Exception:
            logger.exception("Exception in handle_event")
