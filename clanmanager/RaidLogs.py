from discord.ext import commands
from pykollib import Clan
from pykollib.request.clan_raid_log import RaidAction
from pykollib.Error import ClanPermissionsError
from time import time
from datetime import datetime, timedelta
from tqdm import tqdm
from peewee import SQL, JOIN, fn
import asyncio
import json
import re
import traceback
from tabulate import tabulate
import sys

from .DiscordIO import DiscordIO
from .util import pm_only, team_only
from .db import db, Raid, Log

kills_pattern = re.compile(r"Your clan has defeated ([0-9]+) monster\(s\) in the ([A-Za-z]+).")

class RaidLogs(commands.Cog):
    def __init__(self, bot: commands.Bot, clans=[]):
        self.bot = bot
        self.clans = clans
        # self.bg_task = self.bot.loop.create_task(self.monitor_clans(clans))

    async def get_channel(self, context, channel_name: str):
        if channel_name is None:
            return None

        try:
            return next(c for c in self.bot.get_all_channels() if c.name == channel_name)
        except StopIteration:
            await context.send("Cannot find a channel called {}".format(channel_name))
            return None

    async def parse_clan_raid_logs(self, clan_details, message_stream = sys.stdout):
        clan_name, clan_id = clan_details
        kol = self.bot.kol

        clan = Clan(kol, id=clan_id)
        await clan.join()

        try:
            current = await clan.get_raids()
        except ClanPermissionsError:
            message_stream.write("Skipping {} due to lack of basement permissions".format(clan_name))
            return

        previous = await clan.get_previous_raids()

        tasks = []
        created_raids = []
        updated_raids = []

        for data in tqdm(current + previous, desc="Discovering previous raid logs in {}".format(clan_name), file=message_stream, unit="raid logs", leave=False):
            raid = Raid.get_or_none(id=data.id)

            raids_list = updated_raids

            if raid is None:
                raid = Raid(id=data.id, name=data.name, clan_id=clan_id, clan_name=clan_name)
                raids_list = created_raids

            if data.events is None and raid.end is None:
                raid.start = data.start
                raid.end = data.end
                tasks += [asyncio.ensure_future(clan.get_raid_log(data.id))]

            if raid.is_dirty():
                raids_list.append(raid)

        Raid.bulk_create(created_raids, batch_size=50)
        Raid.bulk_update(updated_raids, fields=[Raid.start, Raid.end], batch_size=50)

        raids_data = current + [await t for t in tqdm(asyncio.as_completed(tasks), desc="Loading previous raid logs in {}".format(clan_name), unit="raid logs", total=len(tasks), leave=False, file=message_stream, ascii=False)]

        with tqdm(raids_data, desc="Parsing raid logs in {}".format(clan_name), unit="raids", file=message_stream, ascii=False) as p:
            for data in p:
                raid = Raid.get_or_none(id=data.id)

                if raid is None:
                    p.write("Something went wrong with raid {}".format(data.id))
                    continue

                logs = []

                for category, events in data.events:
                    category = category.rstrip(":")
                    for event in events:
                        turns = int(event.data.pop("turns", 0))

                        event_data = json.dumps(event.data, sort_keys=True)

                        log = Log.get_or_none(
                            Log.raid == raid,
                            Log.category == category,
                            Log.action == event.action,
                            Log.username == event.username,
                            Log.user_id == event.user_id,
                            Log.data == event_data
                        )

                        if log is None:
                            log = Log(
                                raid=raid,
                                category=category,
                                action=event.action,
                                username=event.username,
                                user_id=event.user_id,
                                turns=turns,
                                data=event_data,
                            )
                        elif log.turns != turns:
                            log.turns = turns
                            log.last_updated = time()

                        logs.append(log)

                with db.atomic():
                    Log.delete().where(Log.raid == raid).execute()
                    Log.bulk_create(logs, batch_size=50)
                    raid.summary = json.dumps(data.summary)
                    raid.save()


    async def monitor_clans(self, clans):
        try:
            bot = self.bot
            await bot.wait_until_ready()

            if len(clans) == 0:
                clans = [(bot.kol.state["clan_name"], bot.kol.state["clan_id"])]

            for clan in clans:
                await self.parse_clan_raid_logs(clan)

        except Exception:
            print(traceback.format_exc())

    @commands.command(name="parse_raids")
    @team_only()
    @pm_only()
    async def parse_clans(self, context):
        message = await context.send("Initializing display")
        message_stream = DiscordIO(message)
        for clan in self.clans:
            await self.parse_clan_raid_logs(clan, message_stream)
        message_stream.print("Raid parsing complete")


    @commands.command(name="skills")
    @team_only()
    @pm_only()
    async def skills(self, context, since: str = None, limit: int = None, channel_name: str = None):
        channel = await self.get_channel(context, channel_name)

        since = datetime.strptime(since, "%Y%m%d") if since is not None else datetime.now() - timedelta(days=365)

        if limit is None:
            limit = len(self.clans) * 3
        elif limit == 0:
            limit = None

        Skills = Log.alias()
        skills_query = Skills.select(Skills.user_id,
                                     fn.COUNT(Skills.id).alias("skills"))\
                             .join_from(Skills, Raid)\
                             .where(Skills.action == RaidAction.DreadMachineUse, Raid.start >= since)\
                             .group_by(Skills.user_id)\
                             .alias("sq")

        kills_query = Log.select(Log.username.alias("Username"),
                                 (fn.SUM(Log.turns) / (fn.IFNULL(skills_query.c.skills, 0) + 0.5)).alias("Ranking"))\
                         .join_from(Log, skills_query, JOIN.LEFT_OUTER, on=(Log.user_id == skills_query.c.user_id))\
                         .join_from(Log, Raid)\
                         .where(Log.action == RaidAction.Victory, Raid.name == "dreadsylvania", Raid.start >= since)\
                         .group_by(Log.user_id)\
                         .order_by(SQL("ranking").desc())\
                         .limit(limit)

        rankings = [r for r in kills_query.dicts()]
        table = tabulate(rankings, headers="keys")
        message = "```\n{}\n```".format(table)

        if channel:
            await context.send("Sending skills to {}".format(channel.name))
            await channel.send(message)
        else:
            await context.send(message)

    @commands.command(name="summary")
    @team_only()
    @pm_only()
    async def summary(self, context, channel_name: str = None, description: str = None):
        """
        Post a summary of all the Dreadsylvania instances currently being monitored.

        :param channel_name: Channel to post the summary to. If not specified, the bot will respond
                             to you in a PM
        :param description: Text to appear inline with the summary.
        :return:
        """
        channel = await self.get_channel(context, channel_name)

        message = "__**DREAD UPDATE**__\n\n"

        if description is not None:
            message += "{}\n\n".format(description)

        for raid in Raid.select().where(Raid.name == "dreadsylvania", Raid.end == None):
            summary = json.loads(raid.summary)

            kills = {"forest": 1000, "village": 1000, "castle": 1000}

            for line in summary:
                m = kills_pattern.match(line)
                if m:
                    kills[m.group(2).lower()] -= int(m.group(1))

            extra = None
            if Log.select().where(Log.raid == raid, Log.action == RaidAction.DreadMachineFix).exists():
                machine_uses = Log.select().where(Log.raid == raid, Log.action == RaidAction.DreadMachineUse).count()
                left = 3 - machine_uses
                extra = " ({} skill{} left)".format(left, "" if left == 1 else "s")

            message += "**{}**: {}/{}/{}{}\n".format(raid.clan_name, kills["forest"], kills["village"], kills["castle"], extra or "")

        if channel:
            await context.send("Sending summary to {}".format(channel.name))
            await channel.send(message)
        else:
            await context.send(message)
