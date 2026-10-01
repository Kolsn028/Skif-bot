"""Канал поиска личных каналов для Хай и выше: меню выбора участника, ответ со ссылкой на его канал."""

import discord

from .access import HIGH_KEYS, may_find_rooms
from .interactions import SafeView
from .performance import edit_if_changed
from .roles import configured_roles
from .rooms import channel_link, locate_room
from .ui import panel

NO_MENTIONS = discord.AllowedMentions.none()
BRAND = 0xA82D40
SEARCH_CHANNEL_NAME = 'поиск-каналов'
SEARCH_PREFIX = 'skif:roomsearch:'


def search_topic(bot, guild):
    return f'{SEARCH_PREFIX}{bot.user.id}:{guild.id}'


def search_embed():
    return panel(
        '🔎 Поиск личных каналов',
        'Выбери участника в меню ниже (начни вводить ник): бот пришлёт ссылку на его личный канал. Ответ видишь только ты.',
        [('КТО ВИДИТ', 'Хай, Дэп Овнер и Овнер')],
        BRAND,
    )


class RoomSearchView(SafeView):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.select(
        cls=discord.ui.UserSelect,
        placeholder='Найти участника по нику…',
        min_values=1,
        max_values=1,
        custom_id='skif:roomsearch:user',
    )
    async def pick(self, i, select):
        cfg = await self.bot.db.get_config(i.guild_id)
        if not isinstance(i.user, discord.Member) or not may_find_rooms(i.user, cfg):
            return await i.response.send_message('⛔ Только Хай, Дэп Овнер и Овнер.', ephemeral=True)
        picked = select.values[0]
        member = i.guild.get_member(picked.id) or picked
        channel = await locate_room(self.bot, i.guild, member)
        if not channel:
            return await i.response.send_message(
                f'У {member.mention} нет личного канала: он не зарегистрирован в хабе.', ephemeral=True, allowed_mentions=NO_MENTIONS
            )
        await i.response.send_message(
            f'Личный канал {member.mention}: {channel.mention}', ephemeral=True, view=channel_link(channel), allowed_mentions=NO_MENTIONS
        )


async def install(bot, guild):
    """Создаёт или обновляет канал поиска (видят только Хай и выше) и его панель."""
    cfg = await bot.db.get_config(guild.id)
    category = guild.get_channel(cfg.get('family_category_id') or 0)
    if not isinstance(category, discord.CategoryChannel):
        raise ValueError('Не найдена настроенная категория SKIF • СОСТАВ.')
    ow = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, embed_links=True, read_message_history=True),
    }
    for role in configured_roles(guild, cfg, HIGH_KEYS):
        ow[role] = discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True)
    topic = search_topic(bot, guild)
    matches = [
        c
        for c in guild.channels
        if isinstance(c, discord.TextChannel) and (c.topic == topic or (c.category_id == category.id and c.name == SEARCH_CHANNEL_NAME))
    ]
    if len(matches) > 1:
        raise ValueError(f'Найдены дубли канала {SEARCH_CHANNEL_NAME}.')
    channel = matches[0] if matches else await guild.create_text_channel(SEARCH_CHANNEL_NAME, category=category, topic=topic, overwrites=ow)
    if matches and (channel.category_id != category.id or channel.topic != topic or channel.overwrites != ow):
        await channel.edit(category=category, topic=topic, overwrites=ow)
    message = None
    async for m in channel.history(limit=50):
        if m.author.id == bot.user.id and any((getattr(c, 'custom_id', None) or '').startswith(SEARCH_PREFIX) for row in m.components for c in row.children):
            message = m
            break
    if message:
        await edit_if_changed(message, embed=search_embed(), view=RoomSearchView(bot), allowed_mentions=NO_MENTIONS)
    else:
        await channel.send(embed=search_embed(), view=RoomSearchView(bot), allowed_mentions=NO_MENTIONS)
    print(f'Room search ready | guild={guild.id} | channel={channel.id}')
    return channel
