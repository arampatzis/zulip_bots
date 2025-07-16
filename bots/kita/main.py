"""Main entry for the Kita bot."""

import logging

from rich.logging import RichHandler

from bots.kita.kita import Kita


def main():
    """Entry for the Kita bot."""
    logger = logging.getLogger(__name__)
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler()],
    )
    logger.info("Kita Bot started!")
    kita = Kita()

    try:
        kita.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (KeyboardInterrupt). Exiting gracefully.")


if __name__ == "__main__":
    main()
