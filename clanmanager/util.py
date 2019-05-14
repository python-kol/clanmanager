from discord.ext import commands

def pm_only():
    async def predicate(context):
        if context.guild is not None:
            raise commands.PrivateMessageOnly("This command can only be issued via DM")
        return True
    return commands.check(predicate)

def team_only(position = 13):
    async def predicate(context):
        guild = context.bot.get_guild(context.bot.raid_guild)
        member = guild.get_member(context.author.id)
        if member.top_role.position < position:
            raise commands.MissingPermissions("Not allowed to run this command")
        return True
    return commands.check(predicate)
