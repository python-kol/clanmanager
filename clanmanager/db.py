import os
import peewee


db = peewee.SqliteDatabase(None)

class Model(peewee.Model):
    class Meta:
        database = db


class User(Model):
    kol_id = peewee.IntegerField(primary_key=True)
    discord_id = peewee.IntegerField()
    token = peewee.TextField(null=True)


class Dungeon(Model):
    clan_id = peewee.IntegerField()
    clan_name = peewee.TextField()
    type = peewee.TextField()
    raid_id = peewee.IntegerField(default=0)
    status = peewee.TextField(default="{}")


class Log(Model):
    dungeon = peewee.ForeignKeyField(Dungeon, backref="logs")
    zone = peewee.TextField()
    username = peewee.TextField()
    userid = peewee.IntegerField()
    event = peewee.TextField()
