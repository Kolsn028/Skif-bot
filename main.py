import logging
import os
import discord
from dotenv import load_dotenv

load_dotenv()

from bot.core import SkifBot
from bot.database import Database
from bot.commands import register_commands

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)

# User-approved fresh v9 database. Existing v9 data is reopened, never deleted on restart.
DATABASE_PATH = os.getenv("DATABASE_PATH", "data/skif-v9.db")
log = logging.getLogger(__name__)
log.info('Database storage | path=%s | data_mount=%s', DATABASE_PATH, os.path.ismount(os.path.abspath('data')))

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN не задан. Создай .env по примеру .env.example")

intents = discord.Intents.default()
intents.members = True

bot = SkifBot(command_prefix="!", intents=intents, db=Database(DATABASE_PATH), allowed_mentions=discord.AllowedMentions.none())
register_commands(bot)
bot.run(TOKEN)
