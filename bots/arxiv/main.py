"""Main entry for the Arxiv bot."""

import logging

from rich.logging import RichHandler

from bots.arxiv.arxiv import Arxiv


def main() -> None:
    """Entry for the Arxiv bot."""
    logger = logging.getLogger(__name__)
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler()],
    )

    logger.info("Arxiv Bot started!")
    bot = Arxiv()
    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (KeyboardInterrupt). Exiting gracefully.")
