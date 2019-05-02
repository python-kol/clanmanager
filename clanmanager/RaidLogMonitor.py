from asyncio import sleep
from discord.ext import commands
from itertools import cycle
from pykollib import Clan
import json

from .util import pm_only
from .db import User, Dungeon, Log

class RaidLogMonitor(commands.Cog):
    def __init__(self, bot, clans=[]):
        self.bot = bot
        self.bg_task = self.bot.loop.create_task(self.monitor_clans(clans))

    def monitor_clan(self, clan):
        clan_name, clan_id = clan
        kol = self.bot.kol
        announce = True
        output = []

        Clan(kol, id=clan_id).join()
        logs = kol.clan.getRaidLogs()

        dreadLogs = [e for e in logs["events"] if e["dungeon"] == "Dreadsylvania"]
        status = logs["status"]["Dreadsylvania"]
        raidId = status["raidId"]

        dungeon, created = Dungeon.get_or_create(clan_id=clan_id, clan_name=clan_name, type="dread")

        if created:
            announce = False
        elif dungeon.raid_id < raidId:
            output.append(("reset", None))
            dungeon.delete_instance(recursive=True, delete_nullable=True)

        dungeon.raid_id = raidId

        for log in dreadLogs:
            query = {"zone": log["category"],
                     "event": log["event"],
                     "username": log["userName"],
                     "userid": log["userId"]}

            log, created = Log.get_or_create(dungeon=dungeon, **query)

            if created is False or query["event"].startswith(("defeated", "was defeated by")):
                continue

            output.append(("log", log))

        s = {} if dungeon.status == "" else json.loads(dungeon.status)

        for zone, kills in status.items():
            if zone not in ["castle", "village", "forest"]:
                continue
            if s.get(zone, 0) < kills and kills >= 990:
                output.append(("kills", (zone, kills)))

        dungeon.status = json.dumps(status)
        dungeon.save()

        return output if announce else []

    async def monitor_clans(self, clans):
        bot = self.bot
        await bot.wait_until_ready()

        if len(clans) == 0:
            clans = [(bot.kol.preferences["clanName"], bot.kol.preferences["clanId"])]

        clans.append(None)

        for clan in clans:
            if clan is None:
                await sleep(10)
                continue
            output = self.monitor_clan(clan)
            clan_name, clan_id = clan
            if len(output) > 0:
                message = []
                for type, info in output:
                    if type == "log":
                        user = User.select().where(User.kol_id == info.userid, User.token.is_null())
                        member = None if len(user) == 0 else bot.get_user(user[0].discord_id)
                        mention = info.username if member is None else member.mention
                        message.append("[{}] {} {}".format(clan_name, mention, info.event))
                        continue
                    if type == "kills":
                        zone, kills = info
                        message.append("[{}] {} is at {} kills remaining".format(clan_name, zone, kills))
                        continue
                    if type == "reset":
                        message.append("[{}] Dreadsylvania has been reset".format(clan_name))
                        continue
                await bot.get_channel(bot.raid_channel).send("\n".join(message))

    @commands.command(name="summary")
    @pm_only()
    async def summary(self, context, channel_name: string = None, description: string = None):
        """
        Post a summary of all the Dreadsylvania instances currently being monitored.

        :param channel_name: Channel to post the summary to. If not specified, the bot will respond
                             to you in a PM
        :param description: Text to appear inline with the summary.
        :return:
        """
        if channel_name is not None:
            try:
                channel = next(c for c in self.bot.get_all_channels() if c.name == channel_name)
                member = channel.guild.get_member(context.author.id)
                if member is None or member.top_role.position < 13:
                    await context.send("You do not have permission to post to that channel")
                    return
            except StopIteration:
                await context.send("Cannot find a channel called {}".format(channel_name))
                return

        output = ["__**DREAD UPDATE**__", ""]

        if description is not None:
            output.append(description)
            output.append("")

        for dungeon in Dungeon.select().where(Dungeon.type == "dread"):
            s = json.loads(dungeon.status)
            woods = 1000 - s.get("forest", 0)
            village = 1000 - s.get("village", 0)
            castle = 1000 - s.get("castle", 0)

            extra = ""
            if woods < 11 and village < 11 and castle < 11:
                machine_uses = Log.select().where(Log.dungeon == dungeon, Log.event.startswith("used The Machine")).count()
                left = 3 - machine_uses
                extra = " ({} {} left)".format(left, "skill" if left == 1 else "skills")

            output.append("**{}**: {}/{}/{}{}".format(dungeon.clan_name, woods, village, castle, extra))

        if len(output) == 0:
            await context.send("Summary is empty, doing nothing")
            return

        message = "\n".join(output)
        if channel_name is None:
            await context.send(message)
        else:
            await context.send("Sending summary to {}".format(channel.name))
            await channel.send(message)
