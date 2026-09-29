"""Private contract and promotion workflows. Evidence is checked by staff."""

import discord
from .theme import DANGER, SUCCESS, WARNING
from .interactions import SafeView, SafeModal, private_thread
from .roles import configured_roles, STAFF_KEYS, notify_assistants, notify_recruiters
from .ui import base_embed

RULES = (
    "**1 → 3 ранг**\n"
    "• 10 помощей по контрактам со скриншотами.\n"
    "• 10 скриншотов с разных каптов.\n"
    "• 10 дней в семье.\n"
    "• Пройденный обзвон у рекрутера и активность.\n\n"
    "**2 ранг пропускаем.** После 3 ранга — отдельные заявки и обзвоны.\n"
    "Прикрепи доказательства в приватной ветке. Руководство проверяет каждый пункт.\n"
    "После одобрения бот заменит Academy на main (3 ранг). Права останутся теми же."
)


from .services.ranks import award_main


def contract_panel_embed():
    return base_embed(
        "🟠 Активация контрактов",
        "Нажми **Оформить контракт**, укажи название и выбери: активация или помощь.\n"
        "Прикрепи скриншот в своей приватной ветке. **Рекрут / Хай / Дэп Овнер** проверит отчёт.\n"
        "Для повышения учитывается помощь, а не просто активация.",
        0xE58A35,
    )


def promotion_panel_embed():
    return base_embed("😎 Система повышения", RULES, 0xD5AD65)


def green_panel_embed():
    return base_embed(
        "🟢 Сдача гринов",
        "Нажми **Подать отчёт**, укажи **ник в игре** и приложи скрин с планшета. Отчёт попадёт в приватную ветку, проверяет Рекрут и выше.",
        SUCCESS,
    )


def warn_panel_embed():
    return base_embed(
        "⚠️ Снятие варнов",
        "Нажми **Подать заявку**, укажи **ник в игре** и приложи скриншот сданного контракта или грина. "
        "Заявка попадёт в приватную ветку, проверяет Рекрут и выше.",
        WARNING,
    )


async def submit(bot, i, kind, details):
    if not isinstance(i.user, discord.Member) or not await bot.is_family_member(i.user):
        return await i.response.send_message("Доступно участникам семьи.", ephemeral=True)
    await i.response.defer(ephemeral=True, thinking=True)
    async with bot.operation_locks[("progress_open", i.guild_id, i.user.id)]:
        cfg = await bot.db.get_config(i.guild_id)
        # Try profile hub first, fall back to legacy channel
        from .hub import find_hub

        parent = await find_hub(bot, i.guild)
        if not parent:
            parent = i.guild.get_channel(cfg.get(f"{kind}_panel_channel_id") or 0)
        if not isinstance(parent, discord.TextChannel):
            raise ValueError("Сначала настрой сервер через /setup.")
        existing = await bot.db.find_open_progress(i.guild_id, i.user.id, kind)
        if existing:
            return await i.followup.send(f"У тебя уже есть открытая ветка: <#{existing["thread_id"]}>.", ephemeral=True)
        kind_names = {"contract": "контракт", "promotion": "повышение", "green": "грины", "warn": "варны"}
        thread = await private_thread(
            parent, i.user, configured_roles(i.guild, cfg, STAFF_KEYS), f"{kind_names.get(kind, kind)}-{i.user.display_name}"
        )
        try:
            await bot.db.create_progress(i.guild_id, i.user.id, kind, thread.id, details, bot.now_iso())
            embed = base_embed(
                "🟡 Проверка контракта"
                if kind == "contract"
                else ("🟡 Отчёт: сдача гринов" if kind == "green" else ("🟡 Заявка: снятие варнов" if kind == "warn" else "🟡 Заявка на повышение")),
                f"Участник: {i.user.mention}\n{details}\n\n**Прикрепи скриншоты в эту ветку.**\n"
                + ("Проверяют: Рекрут и выше. " if kind in ("contract", "green", "warn") else "Повышение до 3 ранга проверяет Рекрут и выше. ")
                + "Самостоятельное одобрение запрещено.",
            )
            if kind == "promotion":
                embed.add_field(
                    name="Что проверяет руководство", value="10 помощей • 10 разных каптов • 10 дней в семье • обзвон • активность", inline=False
                )
            await thread.send(embed=embed, view=ProgressReviewView(bot), allowed_mentions=discord.AllowedMentions.none())
        except Exception:
            await bot.db.delete_progress_thread(thread.id)
            await thread.delete(reason="Skif: не удалось открыть заявку")
            raise
        notifier = notify_recruiters if kind == "promotion" else notify_assistants
        await notifier(thread, i.guild, cfg, base_embed("🔔 Нужна проверка", "Новая заявка. Доказательства — в этой ветке."))
        await i.followup.send(f"Готово: {thread.mention}. Загрузи сюда доказательства.", ephemeral=True)


class ContractModal(SafeModal, title="Контракт • Skif"):
    name = discord.ui.TextInput(label="Название контракта", max_length=120)
    mode = discord.ui.TextInput(label="Активация или помощь?", placeholder="активация / помощь", max_length=20)
    event = discord.ui.TextInput(label="Дата / время / номер события", max_length=100)

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, i):
        mode = str(self.mode).strip().lower()
        if mode not in ("активация", "помощь"):
            return await i.response.send_message('В поле типа напиши «активация» или «помощь».', ephemeral=True)
        await submit(self.bot, i, "contract", f"**{mode.capitalize()}** • {self.name}\nСобытие: {self.event}")


class PromotionModal(SafeModal, title="Повышение • 1 → 3"):
    contracts = discord.ui.TextInput(label="10 помощей: ссылки на отчёты", style=discord.TextStyle.paragraph, max_length=1000)
    capts = discord.ui.TextInput(label="10 разных каптов: даты / ссылки", style=discord.TextStyle.paragraph, max_length=1000)
    since = discord.ui.TextInput(label="Дата вступления в семью", max_length=60)
    interview = discord.ui.TextInput(label="Кто провёл обзвон и когда?", max_length=150)
    activity = discord.ui.TextInput(label="Твоя активность в семье", style=discord.TextStyle.paragraph, max_length=300)

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, i):
        await submit(
            self.bot,
            i,
            "promotion",
            f"**Контракты:** {self.contracts}\n**Капты:** {self.capts}\n"
            f"**В семье с:** {self.since}\n**Обзвон:** {self.interview}\n**Активность:** {self.activity}",
        )


class GreenReportModal(SafeModal, title="Сдача гринов • Skif"):
    nickname = discord.ui.TextInput(label="Ник в игре", max_length=60)

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, i):
        await submit(self.bot, i, "green", f"**Ник в игре:** {self.nickname}")


class WarnRemovalModal(SafeModal, title="Снятие варнов • Skif"):
    nickname = discord.ui.TextInput(label="Ник в игре", max_length=60)

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, i):
        await submit(self.bot, i, "warn", f"**Ник в игре:** {self.nickname}")


class ContractPanelView(SafeView):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Оформить контракт", emoji="🟠", style=discord.ButtonStyle.primary, custom_id="skif:contract:open")
    async def open_contract(self, i, _):
        if not isinstance(i.user, discord.Member) or not await self.bot.is_family_member(i.user):
            return await i.response.send_message("Доступно участникам семьи.", ephemeral=True)
        await i.response.send_modal(ContractModal(self.bot))


class PromotionPanelView(SafeView):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Подать на повышение", emoji="📈", style=discord.ButtonStyle.success, custom_id="skif:promotion:open")
    async def open_promotion(self, i, _):
        if not isinstance(i.user, discord.Member) or not await self.bot.is_family_member(i.user):
            return await i.response.send_message("Доступно участникам семьи.", ephemeral=True)
        await i.response.send_modal(PromotionModal(self.bot))


class GreenPanelView(SafeView):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Подать отчёт", emoji="🟢", style=discord.ButtonStyle.success, custom_id="skif:green:open")
    async def open_green(self, i, _):
        if not isinstance(i.user, discord.Member) or not await self.bot.is_family_member(i.user):
            return await i.response.send_message("Доступно участникам семьи.", ephemeral=True)
        await i.response.send_modal(GreenReportModal(self.bot))


class WarnPanelView(SafeView):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Подать заявку", emoji="⚠️", style=discord.ButtonStyle.primary, custom_id="skif:warn:open")
    async def open_warn(self, i, _):
        if not isinstance(i.user, discord.Member) or not await self.bot.is_family_member(i.user):
            return await i.response.send_message("Доступно участникам семьи.", ephemeral=True)
        await i.response.send_modal(WarnRemovalModal(self.bot))


class DecisionModal(SafeModal, title="Решение по заявке"):
    reason = discord.ui.TextInput(label="Что проверено / причина отказа", style=discord.TextStyle.paragraph, max_length=700)
    checklist = discord.ui.TextInput(
        label="Для повышения: 10/10/10/обзвон/активность", placeholder="После проверки напиши: подтверждаю", required=False, max_length=40
    )

    def __init__(self, bot, thread_id, accepted):
        super().__init__()
        self.bot = bot
        self.thread_id = thread_id
        self.accepted = accepted

    async def on_submit(self, i):
        if not isinstance(i.user, discord.Member):
            return await i.response.send_message("Доступно только на сервере.", ephemeral=True)
        await i.response.defer(ephemeral=True, thinking=True)
        async with self.bot.operation_locks[("progress_decision", i.guild_id, self.thread_id)]:
            row = await self.bot.db.progress_by_thread(i.guild_id, self.thread_id)
            if not row or row["kind"] not in ("contract", "promotion", "green", "warn") or row["status"] != "pending":
                return await i.followup.send("Заявка уже закрыта или не найдена.", ephemeral=True)
            allowed = await self.bot.can_promote(i.user) if row["kind"] == "promotion" else await self.bot.is_high_staff(i.user)
            if not allowed:
                return await i.followup.send("Проверка доступна Рекрут и всем старшим ролям.", ephemeral=True)
            if row["member_id"] == i.user.id:
                return await i.followup.send("Свою заявку проверять нельзя.", ephemeral=True)
            member = i.guild.get_member(row["member_id"])
            if self.accepted and (not member or not await self.bot.is_family_member(member)):
                return await i.followup.send("Автор больше не состоит в семье.", ephemeral=True)
            if self.accepted and row["kind"] == "promotion" and str(self.checklist).strip().lower() != "подтверждаю":
                return await i.followup.send("Проверь все пять условий и напиши «подтверждаю».", ephemeral=True)
            if self.accepted and row["kind"] in ("contract", "green", "warn"):
                evidence = False
                async for msg in i.channel.history(limit=None):
                    if msg.author.id == row["member_id"] and any((a.content_type or "").startswith("image/") for a in msg.attachments):
                        evidence = True
                        break
                if not evidence:
                    labels = {"contract": "контракта", "green": "с планшета", "warn": "контракта или грина"}
                    return await i.followup.send(
                        f"Автор ещё не прикрепил скриншот {labels[row["kind"]]} в эту ветку. "
                        "Если скриншот есть, а бот его не видит, Овнеру нужно включить Message Content Intent в Discord Developer Portal.",
                        ephemeral=True,
                    )
            if self.accepted and row["kind"] == "promotion":
                await award_main(self.bot, i.guild, member)
            status = "approved" if self.accepted else "rejected"
            # Publish first; if Discord is unavailable keep the request actionable.
            await i.channel.send(
                embed=base_embed(
                    "✅ Подтверждено" if self.accepted else "❌ Отклонено",
                    f"Участник: <@{row["member_id"]}>\nПроверил: {i.user.mention}\n{self.reason}"
                    + ("\n**3 ранг: main.** Роль Academy заменена; права сохранены." if self.accepted and row["kind"] == "promotion" else ""),
                    SUCCESS if self.accepted else DANGER,
                ),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            await self.bot.db.decide_progress_thread(self.thread_id, status, i.user.id, str(self.reason))
            from .profiles import refresh_member

            await refresh_member(self.bot, i.guild, row["member_id"])
            await i.followup.send("Решение сохранено.", ephemeral=True)
            await i.channel.edit(archived=True, locked=True)


class ProgressReviewView(SafeView):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    async def decide(self, i, accepted):
        row = await self.bot.db.progress_kind_by_thread(i.guild_id, i.channel_id)
        if not row or row["kind"] not in ("contract", "promotion", "green", "warn") or not isinstance(i.user, discord.Member):
            return await i.response.send_message("Заявка не найдена.", ephemeral=True)
        allowed = await self.bot.can_promote(i.user) if row["kind"] == "promotion" else await self.bot.is_high_staff(i.user)
        if not allowed:
            return await i.response.send_message("Нет роли, ответственной за это направление.", ephemeral=True)
        await i.response.send_modal(DecisionModal(self.bot, i.channel_id, accepted))

    @discord.ui.button(label="Подтвердить", style=discord.ButtonStyle.success, custom_id="skif:progress:approve")
    async def approve(self, i, _):
        await self.decide(i, True)

    @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.danger, custom_id="skif:progress:reject")
    async def reject(self, i, _):
        await self.decide(i, False)
