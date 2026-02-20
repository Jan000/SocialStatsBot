"""Entry point for the SocialStatsBot."""

from __future__ import annotations

import logging
import sys
import tomllib
from pathlib import Path

from bot.bot import SocialStatsBot


def main() -> None:
    # Logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Config
    config_path = Path(__file__).resolve().parent / "config.toml"
    if not config_path.exists():
        logging.error("config.toml not found – copy config.toml.example and fill in your keys.")
        sys.exit(1)

    with open(config_path, "rb") as f:
        config = tomllib.load(f)

    bot_token = config["bot"]["token"]
    yt_key = config["api_keys"]["youtube_api_key"]
    tw_id = config["api_keys"]["twitch_client_id"]
    tw_secret = config["api_keys"]["twitch_client_secret"]

    bot = SocialStatsBot(
        youtube_api_key=yt_key,
        twitch_client_id=tw_id,
        twitch_client_secret=tw_secret,
    )
    bot.run(bot_token, log_handler=None)


if __name__ == "__main__":
    main()
