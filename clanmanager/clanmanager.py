import asyncio
from discord.ext import commands
from dotenv import load_dotenv
from pykollib import Session
import os

from .db import db, User, Raid, Log
from .Verification import Verification
from .RaidLogs import RaidLogs

load_dotenv()

clans = [
    ("The Hogs of Destiny", 21459),
    ("The Piglets of Fate", 67356),
    ("The Hogs of Exploitery", 74403),
    ("The 100% of Scientific FACT Club", 84380),
    ("KirbyLlama's Private Dungeon Clan", 2046997188),
    ("Castle Greyhawk", 2046989105),
]

async def main():
    db.init(os.getenv("DB"))
    db.connect()
    db.create_tables([User, Raid, Log])

    async with Session() as kol:
        await kol.login(os.getenv("KOL_USER"), os.getenv("KOL_PASS"))

        bot = commands.Bot("$")
        bot.kol = kol
        bot.raid_guild = int(os.getenv("DISCORD_GUILD"))
        bot.raid_channel = int(os.getenv("DISCORD_CHANNEL"))
        bot.add_cog(Verification(bot))
        bot.add_cog(RaidLogs(bot, clans))
        await bot.login(os.getenv("DISCORD_TOKEN"))
        await bot.connect()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    loop.close()
