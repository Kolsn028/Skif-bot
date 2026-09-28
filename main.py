import logging
import os
import discord
from dotenv import load_dotenv

load_dotenv()

from bot.core import SkifBot
from bot.database import Database

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)

DATABASE_PATH = os.getenv("DATABASE_PATH", "data/skif-v9.db")
log = logging.getLogger(__name__)
log.info('Database storage | path=%s | data_mount=%s', DATABASE_PATH, os.path.ismount(os.path.abspath('data')))

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN не задан. Создай .env по примеру .env.example")

intents = discord.Intents.default()
intents.members = True

bot = SkifBot(command_prefix="!", intents=intents, db=Database(DATABASE_PATH), allowed_mentions=discord.AllowedMentions.none())

# Lazy loading of extensions for faster startup
def load_extensions():
    """Load bot extensions with error handling"""
    extensions = [
        "bot.commands",
        "bot.events",
        "bot.dashboard",
        "bot.profiles",
        "bot.progression",
        "bot.recruiting",
        "bot.roles",
        "bot.roster",
        "bot.tiers",
        "bot.leave",
        "bot.enhancements",
        "bot.performance",
    ]
    
    for ext in extensions:
        try:
            bot.load_extension(ext)
            log.info(f"✓ Loaded extension: {ext}")
        except Exception as e:
            log.error(f"✗ Failed to load {ext}: {e}")

# Load all extensions
load_extensions()

# Run the bot
bot.run(TOKEN)
