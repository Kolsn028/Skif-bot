"""Личный канал участника: приватный канал с постоянными ветками по направлениям.

Ветки нельзя создавать внутри веток, поэтому личное место — отдельный приватный канал.
Каналов в категории не больше 50, поэтому при заполнении бот создаёт «SKIF • ЛИЧНЫЕ 2», «3» и так далее.
"""

import re

import discord

from .roles import STAFF_KEYS, configured_roles
from .ui import panel

NO_MENTIONS = discord.AllowedMentions.none()
BRAND = 0xA82D40
CATEGORY_NAME = 'SKIF • ЛИЧНЫЕ'
CATEGORY_LIMIT = 50
GUILD_CHANNEL_LIMIT = 500
ROOM_THREADS = (
    ('capt', 'капт', '⚔️'),
    ('vzm', 'взм', '🟩'),
    ('vzz', 'взз', '🟦'),
    ('mcl', 'мцл', '🟥'),
    ('green', 'грины', '🟢'),
    ('contract', 'контракт', '🟠'),
    ('warn', 'варны', '⚠️'),
)


def room_topic(bot, guild, member):
    return f'skif:room:{bot.user.id}:{guild.id}:{member.id}'


def room_name(member):
    slug = re.sub(r'[^0-9a-zа-яё]+', '-', str(member.display_name).lower()).strip('-')[:40]
    return f'лк-{slug}' if slug else f'лк-{member.id}'


def find_room_channel(bot, guild, member):
    """Канал по topic: переживает потерю строки в базе."""
    topic = room_topic(bot, guild, member)
    for channel in guild.text_channels:
        if channel.topic == topic:
            return channel
    return None


def _category_number(category):
    match = re.fullmatch(rf'{re.escape(CATEGORY_NAME)}(?: (\d+))?', category.name)
    return int(match.group(1) or 1) if match else None


def room_overwrites(guild, member, staff_roles):
    ow = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            embed_links=True,
            read_message_history=True,
            create_public_threads=True,
            send_messages_in_threads=True,
            manage_threads=True,
        ),
        member: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            send_messages_in_threads=True,
            attach_files=True,
            embed_links=True,
        ),
    }
    for role in staff_roles:
        ow[role] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True, send_messages_in_threads=True, attach_files=True
        )
    return ow


async def pick_category(guild, staff_roles):
    """Первая категория с местом; если все заполнены, создаётся следующая."""
    found = sorted(((n, c) for c in guild.categories if (n := _category_number(c)) is not None), key=lambda x: x[0])
    for _, category in found:
        if len(category.channels) < CATEGORY_LIMIT:
            return category
    number = found[-1][0] + 1 if found else 1
    ow = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_threads=True),
    }
    for role in staff_roles:
        ow[role] = discord.PermissionOverwrite(view_channel=True, read_message_history=True)
    name = CATEGORY_NAME if number == 1 else f'{CATEGORY_NAME} {number}'
    return await guild.create_category(name, overwrites=ow, reason='Skif: личные каналы')


async def find_thread(channel, guild, thread_id, name):
    """Живая ветка по id, иначе по имени (в том числе архивная)."""
    if thread_id:
        thread = guild.get_thread(thread_id)
        if thread and thread.parent_id == channel.id:
            return thread
        try:
            fetched = await guild.fetch_channel(thread_id)
        except discord.HTTPException:
            fetched = None
        if isinstance(fetched, discord.Thread) and fetched.parent_id == channel.id:
            return fetched
    for thread in channel.threads:
        if thread.name == name:
            return thread
    async for thread in channel.archived_threads(limit=50):
        if thread.name == name:
            return thread
    return None


def welcome_embed(member):
    return panel(
        f'🗂️ Личный канал • {member.display_name}',
        'Это твоё личное место в Skif: его видишь ты и руководство. Ниже — постоянные ветки по направлениям, '
        'складывай в них скриншоты и материалы.\n\n'
        + '\n'.join(f'{icon} **{name}**' for _, name, icon in ROOM_THREADS)
        + '\n\nСтатистика, заявки на грины, варны, контракт, повышение и тир — в личном меню по кнопке ниже.',
        [],
        BRAND,
    )


def thread_embed(member, name, icon):
    return panel(
        f'{icon} {name}',
        f'Ветка «{name}» участника {member.mention}. Сюда складывай скриншоты и материалы по этому направлению: их видят ты и руководство.',
        [],
        BRAND,
    )


async def register_member(bot, guild, member):
    """Создаёт личный канал и 7 постоянных веток. Повторный вызов ничего не дублирует. Возвращает (канал, создан_ли_заново)."""
    async with bot.operation_locks[('room_register', guild.id, member.id)]:
        row = await bot.db.get_room(guild.id, member.id)
        channel = guild.get_channel(row['channel_id']) if row else None
        if not isinstance(channel, discord.TextChannel):
            channel = find_room_channel(bot, guild, member)
        known = dict(row['threads']) if row and row['channel_id'] == getattr(channel, 'id', None) else {}
        created = channel is None
        cfg = await bot.db.get_config(guild.id)
        staff = configured_roles(guild, cfg, STAFF_KEYS)
        if created:
            if len(guild.channels) >= GUILD_CHANNEL_LIMIT:
                raise ValueError('На сервере достигнут лимит каналов Discord (500). Удали лишние каналы и повтори.')
            category = await pick_category(guild, staff)
            channel = await guild.create_text_channel(
                room_name(member),
                category=category,
                topic=room_topic(bot, guild, member),
                overwrites=room_overwrites(guild, member, staff),
                reason='Skif: личный канал участника',
            )
        try:
            if created:
                from .hub import PersonalPanelView

                await channel.send(embed=welcome_embed(member), view=PersonalPanelView(bot), allowed_mentions=NO_MENTIONS)
            threads = {}
            for key, name, icon in ROOM_THREADS:
                thread = await find_thread(channel, guild, known.get(key), name)
                if thread is None:
                    thread = await channel.create_thread(
                        name=name,
                        type=discord.ChannelType.public_thread,
                        auto_archive_duration=10080,
                        reason='Skif: личная ветка',
                    )
                    await thread.send(embed=thread_embed(member, name, icon), allowed_mentions=NO_MENTIONS)
                    try:
                        await thread.add_user(member)
                    except discord.HTTPException:
                        pass
                threads[key] = thread.id
        except Exception:
            if created:
                try:
                    await channel.delete(reason='Skif: не удалось создать личный канал')
                except discord.HTTPException:
                    pass
            raise
        await bot.db.save_room(guild.id, member.id, channel.id, threads, bot.now_iso())
        return channel, created


async def locate_room(bot, guild, member):
    """Личный канал участника или None: сначала база, затем topic."""
    row = await bot.db.get_room(guild.id, member.id)
    channel = guild.get_channel(row['channel_id']) if row else None
    if isinstance(channel, discord.TextChannel):
        return channel
    return find_room_channel(bot, guild, member)
