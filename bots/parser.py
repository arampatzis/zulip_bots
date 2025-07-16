"""Parse a Zulip bot message using docopt and shlex."""

import re
import shlex

from docopt import docopt


def parse_zulip_message(message, doc):
    """Parse a Zulip bot message using docopt and shlex.

    This function extracts the bot command or prompt from a Zulip message that mentions
    the bot (e.g., "@**kita** ..."). It attempts to tokenize the message using shlex,
    then parses it using docopt against the provided usage docstring.

    Behavior:
      - If the message matches a documented command or option
        (e.g., "--help", "--reset"),
        it is parsed using shlex and docopt, and the resulting arguments/options dict
        is returned.
      - If shlex raises a ValueError (such as for invalid escape sequences), the message
        is treated as a free-form prompt and returned as {'<prompt>': [prompt]}.
      - If '--help' or '-h' is present among the tokens, a dict with help information is
        returned.
      - If docopt fails to parse the arguments, help information is returned as well.
      - If the message does not mention the bot, None is returned.

    Args:
        message (str): The full Zulip message text, including the bot mention.
        doc (str): The usage docstring for docopt.

    Returns:
        dict or None: Parsed command/option dictionary suitable for further processing,
                      or None if the message doesn't mention the bot.
                      On error, returns {'<prompt>': [prompt]} or help dict as
                      described above.

    Example:
        message = "@**kita** --reset"
        args = parse_zulip_message(message, doc)

    """
    # Remove the Zulip mention (e.g. @**kita**)
    match = re.match(r"@[*]{2}\w+[*]{2}\s+(.*)", message)
    if not match:
        return None
    cmdline = "bot " + match.group(1).strip()

    try:
        tokens = shlex.split(cmdline)
    except ValueError:
        # If shlex fails, treat the entire text as a prompt
        # Optionally, you could log or report the error here
        prompt = match.group(1).strip()
        return {"<prompt>": [prompt]}

    # Help shortcut
    if "--help" in tokens or "-h" in tokens:
        return {"help": True, "help_message": doc}

    try:
        args = docopt(doc, argv=tokens[1:])  # Remove 'bot' for docopt
    except SystemExit:
        return {"help": True, "help_message": doc}

    return args
