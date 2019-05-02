from discord.ext import commands

def pm_only():
    async def predicate(context):
        if context.guild is not None:
            raise PrivateMessageOnly('This command can only be issued via DM')
        return True
    return commands.check(predicate)
