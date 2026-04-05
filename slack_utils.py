from slack_sdk.errors import SlackApiError


def resolve_channel_id(client, channel_ref: str) -> str:
    channel_name = channel_ref.lstrip("#")

    response = client.conversations_list(
        types="public_channel",
        limit=1000,
    )
    for channel in response.get("channels", []):
        if channel.get("name") == channel_name:
            return channel["id"]

    return channel_ref


def ensure_channel_membership(client, channel_ref: str) -> str:
    channel_id = resolve_channel_id(client, channel_ref)
    try:
        client.conversations_join(channel=channel_id)
    except SlackApiError as exc:
        error = exc.response.get("error") if exc.response else None
        if error not in {"method_not_supported_for_channel_type", "not_in_channel", "already_in_channel"}:
            raise
    return channel_id


def post_blocks_with_auto_join(client, channel_ref: str, blocks: list[dict]) -> None:
    channel_id = ensure_channel_membership(client, channel_ref)
    try:
        client.chat_postMessage(channel=channel_id, blocks=blocks)
    except SlackApiError as exc:
        error = exc.response.get("error") if exc.response else None
        if error == "not_in_channel":
            channel_id = ensure_channel_membership(client, channel_ref)
            client.chat_postMessage(channel=channel_id, blocks=blocks)
        else:
            raise