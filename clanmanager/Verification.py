from discord.ext import commands
from pykollib import Error
from uuid import uuid4

from .util import pm_only
from .db import User

class Verification(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @pm_only()
    async def associate(self, context, kol_id: int = None):
        """ Member is asking to associate their Discord and KoL accounts """
        if kol_id is None:
            await context.send("Please specify your KoL id")
            return

        member = context.author
        token = str(uuid4())[:8]
        User.replace(kol_id=kol_id, discord_id=member.id, token=token).execute()
        try:
            self.bot.kol.kmail.send(recipient=kol_id, message="$verify {}".format(token))
            await context.send("Verification token sent to your account via kmail. Paste the command from there into this DM.")
        except Error.USER_NOT_FOUND:
            await context.send("User id is invalid")
        except:
            await context.send("There was an error sending you a kmail")

    @commands.command()
    @pm_only()
    async def verify(self, context, token=None):
        """ Member is completing the verification process """
        if token is None:
            await context.send("You must specify a token")
            return

        member = context.author
        user = User.get_or_none(discord_id=member.id, token=token)
        if user is None:
            await context.send("That verification token is invalid.")
            return

        user.token = None
        user.save()
        await context.send("Verification complete")
