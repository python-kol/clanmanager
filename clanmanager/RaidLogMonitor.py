from discord.ext import commands
from itertools import cycle
from pykollib import Clan
import json

from .util import pm_only
from .db import Dungeon, Log

class RaidLogMonitor(commands.Cog):
    def __init__(self, bot, clans=[]):
        self.bot = bot
        self.bg_task = self.bot.loop.create_task(self.monitor_clans(clans))

    def monitor_clan(self, clan_id):
        kol = self.bot.kol
        announce = True
        output = []

        if kol.preferences["clanId"] != clan_id:
            Clan(kol, id=clan_id).join()
        logs = kol.clan.getRaidLogs()
        clan_name = kol.preferences["clanName"]

        dreadLogs = [e for e in logs["events"] if e["dungeon"] == "Dreadsylvania"]
        status = logs["status"]["Dreadsylvania"]
        raidId = status["raidId"]

        dungeon, created = Dungeon.get_or_create(clan_id=clan_id, clan_name=clan_name, type="dread")

        if created:
            announce = False
        elif dungeon.raid_id < raidId:
            output.append(("reset"))
            dungeon.delete_instance(recursive=True)

        dungeon.raid_id = raidId

        for log in dreadLogs:
            query = {"zone": log["category"],
                     "event": log["event"],
                     "username": log["userName"],
                     "userid": log["userId"]}

            log, created = Log.get_or_create(dungeon=dungeon, **query)

            if created is False or query["event"].startswith(("defeated", "was defeated by")):
                continue

            output.append(('log', log))

        s = {} if dungeon.status == "" else json.loads(dungeon.status)

        for zone, kills in status.items():
            if zone == "kisses":
                continue

            if s.get(zone, 0) < kills and kills >= 990:
                output.append(("kills", (zone, kills)))

        dungeon.status = json.dumps(status)
        dungeon.save()

        return output if announce else []

    async def monitor_clans(self, clans):
        await self.bot.wait_until_ready()

        if len(clans) == 0:
            clans = [self.bot.kol.preferences["clanId"]]

        for clan in cycle(clans):
            output = self.monitor_clan(clan)
            if len(output) > 0:
                print("Sending new actions to the channel")
                print(output)
            await sleep(10)

    @commands.command()
    @pm_only()
    async def kills(self, context):
        output = []
        for dungeon in Dungeon.select().where(Dungeon.type == "dread"):
            s = json.loads(dungeon.status)
            woods = 1000 - s.get("forest", 0)
            village = 1000 - s.get("village", 0)
            castle = 1000 - s.get("castle", 0)

            f = "**" if woods < 11 and village < 11 and castle < 11 else ""

            output.append("{}{}: {}/{}/{}{}".format(f, dungeon.clan_name, woods, village, castle, f))
        if len(output) > 0:
            await context.send("\n".join(output))
