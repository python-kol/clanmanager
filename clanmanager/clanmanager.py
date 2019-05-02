from asyncio import sleep
from discord.ext import commands
from dotenv import load_dotenv
from pykollib import Session
import atexit
import os

from .db import db, User, Dungeon, Log
from .Verification import Verification
from .RaidLogMonitor import RaidLogMonitor

load_dotenv()

def main():
    db.init(os.getenv("DB"))
    db.connect()
    db.create_tables([User, Dungeon, Log])

    kol = Session()
    kol.login(os.getenv("KOL_USER"), os.getenv("KOL_PASS"))

    bot = commands.Bot("$")
    bot.kol = kol
    bot.add_cog(Verification(bot))
    bot.add_cog(RaidLogMonitor(bot))
    bot.run(os.getenv("DISCORD_TOKEN"))

    atexit.register(lambda: kol.logout())

if __name__ == '__main__':
    main()
