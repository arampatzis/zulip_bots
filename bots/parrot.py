import zulip

client = zulip.Client(config_file="zuliprc")


def main():
    print("Zulip Echo Bot started.")
    # Listen for messages
    client.call_on_each_event(handle_event, event_types=["message"])


def handle_event(event):
    message = event["message"]
    content = message["content"]
    # Avoid replying to self
    if message["sender_email"] == client.email:
        return
    client.send_message(
        {
            "type": message["type"],
            "to": message["display_recipient"],
            "subject": message.get("subject", ""),  # topic for streams
            "content": f"You said: {content}",
        }
    )


if __name__ == "__main__":
    main()
