"""
Entry point – load config and run the bot.
"""

import asyncio
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bot.bot import SocialStatsBot, load_config


def main() -> None:
    config = load_config()
    bot = SocialStatsBot(config)
    bot.run(config["bot"]["token"])


if __name__ == "__main__":
    main()
