"""Profile hub: single channel for all member applications."""

import discord
from .interactions import SafeView, SafeModal, private_thread
from .roles import configured_roles, STAFF_KEYS
from .ui import base_embed
from .performance import edit_if_changed
from .access import TIER_GUILD_ID as GUILD_ID, TIERCHECK_ROLE_ID, may_review_tiers


def hub_topic(bot, guild):
    return f"skif:hub:{bot.user.id}:{guild.id}"


async def find_hub(bot, guild):
    """Find profile hub channel by topic."""
    topic = hub_topic(bot, guild)
    for channel in guild.channels:
        if isinstance(channel, discord.TextChannel) and channel.topic == topic:
            return channel
    return None


class TierChoiceView(SafeView):
    """Ephemeral view for tier selection."""

    def __init__(self, bot):
        super().__init__(timeout=120)
        self.bot = bot

    @discord.ui.select(
        placeholder="Выбери тир для заявки",
        options=[
            discord.SelectOption(label="Тир 1", value="1", description="Серебряный тир"),
            discord.SelectOption(label="Тир 2", value="2", description="Золотой тир"),
            discord.SelectOption(label="Тир 3", value="3", description="Розовый тир"),
        ],
        custom_id="skif:hub:tier_select",
    )
    async def tier_select(self, i, select):
        if not isinstance(i.user, discord.Member) or not await self.bot.is_family_member(i.user):
            return await i.response.send_message("Заявки доступны участникам Skif.", ephemeral=True)
        tier = int(select.values[0])
        from .tiers import TierModal

        await i.response.send_modal(TierModal(self.bot, tier))


class ProfileHubView(SafeView):
    """Persistent panel for profile applications."""

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Сдать грин", emoji="🟢", style=discord.ButtonStyle.success, custom_id="skif:hub:green")
    async def green(self, i, _):
        if not isinstance(i.user, discord.Member) or not await self.bot.is_family_member(i.user):
            return await i.response.send_message("Доступно участникам семьи.", ephemeral=True)
        from .progression import GreenReportModal

        await i.response.send_modal(GreenReportModal(self.bot))

    @discord.ui.button(label="Снять варн", emoji="⚠️", style=discord.ButtonStyle.primary, custom_id="skif:hub:warn")
    async def warn(self, i, _):
        if not isinstance(i.user, discord.Member) or not await self.bot.is_family_member(i.user):
            return await i.response.send_message("Доступно участникам семьи.", ephemeral=True)
        from .progression import WarnRemovalModal

        await i.response.send_modal(WarnRemovalModal(self.bot))

    @discord.ui.button(label="Контракт", emoji="🟠", style=discord.ButtonStyle.primary, custom_id="skif:hub:contract")
    async def contract(self, i, _):
        if not isinstance(i.user, discord.Member) or not await self.bot.is_family_member(i.user):
            return await i.response.send_message("Доступно участникам семьи.", ephemeral=True)
        from .progression import ContractModal

        await i.response.send_modal(ContractModal(self.bot))

    @discord.ui.button(label="Повышение", emoji="📈", style=discord.ButtonStyle.success, custom_id="skif:hub:promotion")
    async def promotion(self, i, _):
        if not isinstance(i.user, discord.Member) or not await self.bot.is_family_member(i.user):
            return await i.response.send_message("Доступно участникам семьи.", ephemeral=True)
        from .progression import PromotionModal

        await i.response.send_modal(PromotionModal(self.bot))

    @discord.ui.button(label="Заявка на тир", emoji="🏆", style=discord.ButtonStyle.secondary, custom_id="skif:hub:tier")
    async def tier(self, i, _):
        if not isinstance(i.user, discord.Member) or not await self.bot.is_family_member(i.user):
            return await i.response.send_message("Заявки доступны участникам Skif.", ephemeral=True)
        cfg = await self.bot.db.get_config(i.guild_id)
        if not may_review_tiers(i.user, i.guild_id, cfg):
            return await i.response.send_message("Для заявок на тир нужна роль tiercheck.", ephemeral=True)
        await i.response.send_message(view=TierChoiceView(self.bot), ephemeral=True)


async def install(bot, guild):
    """Create or update profile hub channel and panel."""
    cfg = await bot.db.get_config(guild.id)
    category = guild.get_channel(cfg.get("family_category_id") or 0)
    if not isinstance(category, discord.CategoryChannel):
        raise ValueError("Не найдена настроенная категория SKIF • СОСТАВ.")

    family_roles = configured_roles(guild, cfg, STAFF_KEYS + ("family_role_id", "accepted_role_id", "main_role_id"))
    ow = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            embed_links=True,
            read_message_history=True,
            create_private_threads=True,
            send_messages_in_threads=True,
            manage_threads=True,
        ),
    }
    for role in family_roles:
        ow[role] = discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True, send_messages_in_threads=True)

    topic = hub_topic(bot, guild)
    name = "профиль"

    matches = [c for c in guild.channels if isinstance(c, discord.TextChannel) and (c.topic == topic or (c.category_id == category.id and c.name == name))]
    if len(matches) > 1:
        raise ValueError(f"Найдены дубли канала {name}.")

    channel = matches[0] if matches else await guild.create_text_channel(name, category=category, topic=topic, overwrites=ow)
    if matches and (channel.category_id != category.id or channel.topic != topic or channel.overwrites != ow):
        await channel.edit(category=category, topic=topic, overwrites=ow)

    message = None
    async for m in channel.history(limit=50):
        if m.author.id == bot.user.id and any(getattr(c, "custom_id", "").startswith("skif:hub:") for row in m.components for c in row.children):
            message = m
            break

    embed = base_embed("📋 Профиль и заявки", "Откройте нужную форму. Каждая заявка создаётся в вашей приватной ветке.", 0x5865F2)

    if message:
        await edit_if_changed(message, embed=embed, view=ProfileHubView(bot), allowed_mentions=discord.AllowedMentions.none())
    else:
        await channel.send(embed=embed, view=ProfileHubView(bot), allowed_mentions=discord.AllowedMentions.none())

    print(f"Profile hub ready | guild={guild.id} | channel={channel.id}")
