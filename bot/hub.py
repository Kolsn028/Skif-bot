"""Личный кабинет участника: общая панель в канале «профиль», меню открывается лично для каждого."""

from datetime import datetime, timedelta, timezone

import discord

from .access import TIER_GUILD_ID as GUILD_ID
from .interactions import SafeView
from .performance import edit_if_changed
from .profiles import records
from .roles import STAFF_KEYS, configured_roles
from .services.ranks import TIER_ROLES
from .ui import FOOTER_TEXT, panel

HUB_TITLE = '🪪 Личный кабинет'
NO_MENTIONS = discord.AllowedMentions.none()
BRAND = 0xA82D40
VACATION_COLOR = 0xC69B59
OPEN_KINDS = {
    'green': ('🟢', 'Грины'),
    'warn': ('⚠️', 'Варны'),
    'contract': ('🟠', 'Контракт'),
    'promotion': ('📈', 'Повышение'),
    'tier': ('🏆', 'Тир'),
}
GOAL = 10  # условия перехода на 3 ранг: 10 помощей, 10 каптов, 10 дней


def hub_topic(bot, guild):
    return f'skif:hub:{bot.user.id}:{guild.id}'


async def find_hub(bot, guild):
    """Find profile hub channel by topic."""
    topic = hub_topic(bot, guild)
    for channel in guild.channels:
        if isinstance(channel, discord.TextChannel) and channel.topic == topic:
            return channel
    return None


def bar(value, total=GOAL):
    filled = max(0, min(value, total))
    return '▰' * filled + '▱' * (total - filled)


def stamp(value):
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def approved(rows, kind):
    return [r for r in rows if r['kind'] == kind and r['status'] == 'approved']


def current_tier(member, cfg):
    for n in (3, 2, 1):
        role_id = cfg.get(f'tier_{n}_role_id') or TIER_ROLES.get(n)
        if role_id and member.get_role(role_id):
            return n
    return 0


async def open_requests(bot, guild_id, member_id):
    found = {}
    for kind in ('green', 'warn', 'contract', 'promotion'):
        row = await bot.db.find_open_progress(guild_id, member_id, kind)
        if row:
            found[kind] = row['thread_id']
    tier = await bot.db.find_open_tier(guild_id, member_id)
    if tier:
        found['tier'] = tier['thread_id']
    return found


async def collect(bot, guild, member):
    """Всё, что показывает личное меню. Считается по данным бота при каждом открытии."""
    cfg = await bot.db.get_config(guild.id)
    rows = await records(bot.db, guild.id, member.id)
    now = datetime.now(timezone.utc)
    recent = [r for r in rows if stamp(r['date']) >= now - timedelta(days=30)]
    case = await bot.db.get_case_by_member(guild.id, member.id)
    since = stamp(case['created_at']) if case else (member.joined_at or now)
    vacation = await bot.db.pending_vacation_for_member(guild.id, member.id)
    main_id, accepted_id = cfg.get('main_role_id'), cfg.get('accepted_role_id')
    has_main = bool(main_id and member.get_role(main_id))
    capts = {
        r.get('event_id') or r['key'] for r in rows if r['category'] == 'capt' and r['status'] == 'approved' and r['kind'] in ('visit', 'report')
    }
    role = next((r for r in reversed(member.roles) if not r.is_default()), None)
    return {
        'rank': role.name if role else 'Участник',
        'on_vacation': bool(vacation and vacation['status'] in ('applying', 'approved', 'return_pending', 'restoring')),
        'visits': (len(approved(recent, 'visit')), len(approved(rows, 'visit'))),
        'reports': (len(approved(recent, 'report')), len(approved(rows, 'report'))),
        'contracts': (len(approved(recent, 'contract')), len(approved(rows, 'contract'))),
        'points': sum(r['points'] for r in approved(recent, 'report')),
        'tier': current_tier(member, cfg),
        'since': since,
        'days': max(0, (now - since).days),
        'helps': sum(r['title'].startswith('**Помощь**') for r in approved(rows, 'contract')),
        'capts': len(capts),
        'has_main': has_main,
        'on_path': bool(accepted_id and member.get_role(accepted_id)) and not has_main,
        'open': await open_requests(bot, guild.id, member.id),
        'tiers_here': guild.id == GUILD_ID,
    }


def cabinet_embed(member, d):
    state = '🌴 На отдыхе' if d['on_vacation'] else '🟢 В составе'
    e = panel(
        f'🪪 {member.display_name}', f'**{discord.utils.escape_markdown(d["rank"])}**  ·  {state}', [], VACATION_COLOR if d['on_vacation'] else BRAND
    )
    e.set_image(url=None)
    e.set_thumbnail(url=member.display_avatar.url)
    for name, (recent, total) in (('ПОСЕЩЕНИЯ', d['visits']), ('ОТЧЁТЫ', d['reports']), ('КОНТРАКТЫ', d['contracts'])):
        e.add_field(name=name, value=f'**{recent}**\nза 30 дн. · всего {total}', inline=True)
    e.add_field(name='БАЛЛЫ', value=f'**{d["points"]}**\nза 30 дн.', inline=True)
    e.add_field(name='ТИР', value=f'**Тир {d["tier"]}**\nвыдан' if d['tier'] else '**—**\nне выдан', inline=True)
    e.add_field(name='В СЕМЬЕ', value=f'**{d["days"]} дн.**\nс <t:{int(d["since"].timestamp())}:d>', inline=True)
    if d['on_path']:
        goals = (('🟠', 'Помощи по контрактам', d['helps']), ('⚔️', 'Разные капты', d['capts']), ('📅', 'Дней в семье', d['days']))
        lines = [f'{icon} {name}\n`{bar(n)}` **{min(n, GOAL)}/{GOAL}**' for icon, name, n in goals]
        done = all(n >= GOAL for _, _, n in goals)
        lines.append('✅ Условия по данным бота выполнены: можно подавать заявку.' if done else '_Обзвон и активность проверяет руководство._')
        e.add_field(name='📈 ПУТЬ К 3 РАНГУ', value='\n'.join(lines), inline=False)
    if d['open']:
        value = '\n'.join(f'{OPEN_KINDS[k][0]} **{OPEN_KINDS[k][1]}** → <#{thread}>' for k, thread in d['open'].items())
    else:
        value = 'Открытых заявок нет.'
    e.add_field(name='📂 ОТКРЫТЫЕ ЗАЯВКИ', value=value, inline=False)
    e.set_footer(text=f'{FOOTER_TEXT} • видно только тебе')
    return e


async def history_embed(bot, guild, member):
    rows = (await records(bot.db, guild.id, member.id))[:10]
    lines = []
    for r in rows:
        title = discord.utils.escape_markdown(r['title'])[:70]
        detail = discord.utils.escape_markdown(' '.join(r['detail'].split()))[:90]
        lines.append(f'<t:{int(stamp(r["date"]).timestamp())}:d> · [{title}]({r["url"]})\n> {detail}')
    e = panel('📜 Моя история', '\n\n'.join(lines) or 'Записей пока нет: первая появится после отчёта, контракта или МП.', [], BRAND)
    e.set_image(url=None)
    e.set_thumbnail(url=member.display_avatar.url)
    e.set_footer(text=f'{FOOTER_TEXT} • последние 10 записей · видно только тебе')
    return e


class TierChoiceView(SafeView):
    """Ephemeral view for tier selection."""

    def __init__(self, bot):
        super().__init__(timeout=120)
        self.bot = bot

    @discord.ui.select(
        placeholder='Выбери тир для заявки',
        options=[
            discord.SelectOption(label='Тир 1', value='1', description='Серебряный тир'),
            discord.SelectOption(label='Тир 2', value='2', description='Золотой тир'),
            discord.SelectOption(label='Тир 3', value='3', description='Розовый тир'),
        ],
    )
    async def tier_select(self, i, select):
        if not isinstance(i.user, discord.Member) or not await self.bot.is_family_member(i.user):
            return await i.response.send_message('Заявки доступны участникам Skif.', ephemeral=True)
        from .tiers import TierModal

        await i.response.send_modal(TierModal(self.bot, int(select.values[0])))


async def open_form(bot, i, kind):
    """Общая точка входа для кнопок меню и старых кнопок хаба. Права проверяются здесь, а не по виду кнопки."""
    if not isinstance(i.user, discord.Member) or not await bot.is_family_member(i.user):
        return await i.response.send_message('Доступно участникам семьи.', ephemeral=True)
    if kind == 'tier':
        # Подать заявку может любой участник семьи; проверяет её только tiercheck (см. tiers.py).
        if i.guild_id != GUILD_ID:
            return await i.response.send_message('Раздел тиров не настроен для этого сервера.', ephemeral=True)
        return await i.response.send_message(view=TierChoiceView(bot), ephemeral=True)
    from . import progression

    modal = {
        'green': progression.GreenReportModal,
        'warn': progression.WarnRemovalModal,
        'contract': progression.ContractModal,
        'promotion': progression.PromotionModal,
    }[kind]
    await i.response.send_modal(modal(bot))


class CabinetView(SafeView):
    """Личное меню: живёт в ephemeral-сообщении, поэтому без постоянных custom_id."""

    def __init__(self, bot, owner_id):
        super().__init__(timeout=600)
        self.bot = bot
        self.owner_id = owner_id
        self.origin = None

    async def interaction_check(self, i):
        if i.user.id != self.owner_id:
            await i.response.send_message('Это личное меню другого участника.', ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.origin:
            try:
                await self.origin.edit_original_response(view=None)
            except discord.HTTPException:
                pass

    async def show(self, i, embed, view):
        view.origin = self.origin
        self.stop()  # иначе таймер старого экрана уберёт кнопки у нового
        await i.edit_original_response(embed=embed, view=view, allowed_mentions=NO_MENTIONS)


class MemberMenuView(CabinetView):
    def __init__(self, bot, owner_id, data):
        super().__init__(bot, owner_id)
        for kind, button in (('green', self.green), ('warn', self.warn), ('contract', self.contract), ('promotion', self.promotion)):
            if kind in data['open']:
                self.lock(button, f'{OPEN_KINDS[kind][1]} · на проверке')
        if data['has_main']:
            self.lock(self.promotion, 'Повышение · у тебя 3 ранг')
        if 'tier' in data['open']:
            self.lock(self.tier, 'Тир · на проверке')
        elif not data['tiers_here']:
            self.lock(self.tier, 'Тиры недоступны')

    @staticmethod
    def lock(button, text):
        button.label = text
        button.disabled = True
        button.style = discord.ButtonStyle.secondary

    @discord.ui.button(label='Сдать грин', emoji='🟢', style=discord.ButtonStyle.success, row=0)
    async def green(self, i, _):
        await open_form(self.bot, i, 'green')

    @discord.ui.button(label='Снять варн', emoji='⚠️', style=discord.ButtonStyle.primary, row=0)
    async def warn(self, i, _):
        await open_form(self.bot, i, 'warn')

    @discord.ui.button(label='Контракт', emoji='🟠', style=discord.ButtonStyle.primary, row=0)
    async def contract(self, i, _):
        await open_form(self.bot, i, 'contract')

    @discord.ui.button(label='Повышение', emoji='📈', style=discord.ButtonStyle.success, row=1)
    async def promotion(self, i, _):
        await open_form(self.bot, i, 'promotion')

    @discord.ui.button(label='Тир', emoji='🏆', style=discord.ButtonStyle.secondary, row=1)
    async def tier(self, i, _):
        await open_form(self.bot, i, 'tier')

    @discord.ui.button(label='История', emoji='📜', style=discord.ButtonStyle.secondary, row=1)
    async def history(self, i, _):
        await i.response.defer()
        await self.show(i, await history_embed(self.bot, i.guild, i.user), HistoryView(self.bot, self.owner_id))

    @discord.ui.button(emoji='🔄', style=discord.ButtonStyle.secondary, row=1)
    async def reload(self, i, _):
        await i.response.defer()
        embed, view = await build_menu(self.bot, i.guild, i.user)
        await self.show(i, embed, view)


class HistoryView(CabinetView):
    @discord.ui.button(label='Назад', emoji='◀️', style=discord.ButtonStyle.secondary)
    async def back(self, i, _):
        await i.response.defer()
        embed, view = await build_menu(self.bot, i.guild, i.user)
        await self.show(i, embed, view)


async def build_menu(bot, guild, member):
    data = await collect(bot, guild, member)
    return cabinet_embed(member, data), MemberMenuView(bot, member.id, data)


class ProfileHubView(SafeView):
    """Единая постоянная панель: каждому участнику кнопка открывает его личное меню."""

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label='Открыть мой профиль', emoji='🪪', style=discord.ButtonStyle.primary, custom_id='skif:hub:me')
    async def me(self, i, _):
        if not isinstance(i.user, discord.Member) or not await self.bot.is_family_member(i.user):
            return await i.response.send_message('Личный кабинет доступен участникам семьи.', ephemeral=True)
        await i.response.defer(ephemeral=True)
        embed, view = await build_menu(self.bot, i.guild, i.user)
        view.origin = i
        await i.followup.send(embed=embed, view=view, ephemeral=True, allowed_mentions=NO_MENTIONS)


class LegacyHubView(SafeView):
    """Кнопки прежней панели хаба. Не показываются, но пока такие сообщения есть на сервере, кнопки должны работать."""

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label='Сдать грин', emoji='🟢', style=discord.ButtonStyle.success, custom_id='skif:hub:green')
    async def green(self, i, _):
        await open_form(self.bot, i, 'green')

    @discord.ui.button(label='Снять варн', emoji='⚠️', style=discord.ButtonStyle.primary, custom_id='skif:hub:warn')
    async def warn(self, i, _):
        await open_form(self.bot, i, 'warn')

    @discord.ui.button(label='Контракт', emoji='🟠', style=discord.ButtonStyle.primary, custom_id='skif:hub:contract')
    async def contract(self, i, _):
        await open_form(self.bot, i, 'contract')

    @discord.ui.button(label='Повышение', emoji='📈', style=discord.ButtonStyle.success, custom_id='skif:hub:promotion')
    async def promotion(self, i, _):
        await open_form(self.bot, i, 'promotion')

    @discord.ui.button(label='Заявка на тир', emoji='🏆', style=discord.ButtonStyle.secondary, custom_id='skif:hub:tier')
    async def tier(self, i, _):
        await open_form(self.bot, i, 'tier')


def hub_embed(bot):
    e = panel(
        HUB_TITLE,
        'Всё, что нужно участнику Skif, в одном месте. Нажми кнопку ниже: меню откроется **только для тебя**.',
        [
            (
                'В КАБИНЕТЕ',
                '📊 Твоя статистика и баллы\n📈 Путь к 3 рангу с прогрессом\n📂 Открытые заявки одним списком\n📜 История последних действий',
            ),
            ('МОЖНО ПОДАТЬ', '🟢 Сдачу гринов  ·  ⚠️ Снятие варнов\n🟠 Контракт  ·  📈 Повышение\n🏆 Заявку на тир'),
            (
                'КАК ЭТО РАБОТАЕТ',
                'Каждая заявка создаётся в **приватной ветке**: её видишь ты и проверяющие. Прикрепи скриншоты в ветку и дождись решения.',
            ),
        ],
        BRAND,
    )
    avatar = getattr(getattr(bot, 'user', None), 'display_avatar', None)
    if avatar:
        e.set_thumbnail(url=avatar.url)
    return e


async def install(bot, guild):
    """Create or update profile hub channel and panel."""
    cfg = await bot.db.get_config(guild.id)
    category = guild.get_channel(cfg.get('family_category_id') or 0)
    if not isinstance(category, discord.CategoryChannel):
        raise ValueError('Не найдена настроенная категория SKIF • СОСТАВ.')

    family_roles = configured_roles(guild, cfg, STAFF_KEYS + ('family_role_id', 'accepted_role_id', 'main_role_id'))
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
    name = 'профиль'

    matches = [
        c for c in guild.channels if isinstance(c, discord.TextChannel) and (c.topic == topic or (c.category_id == category.id and c.name == name))
    ]
    if len(matches) > 1:
        raise ValueError(f'Найдены дубли канала {name}.')

    channel = matches[0] if matches else await guild.create_text_channel(name, category=category, topic=topic, overwrites=ow)
    if matches and (channel.category_id != category.id or channel.topic != topic or channel.overwrites != ow):
        await channel.edit(category=category, topic=topic, overwrites=ow)

    message = None
    async for m in channel.history(limit=50):
        if m.author.id == bot.user.id and any(
            (getattr(c, 'custom_id', None) or '').startswith('skif:hub:') for row in m.components for c in row.children
        ):
            message = m
            break

    embed = hub_embed(bot)
    if message:
        await edit_if_changed(message, embed=embed, view=ProfileHubView(bot), allowed_mentions=NO_MENTIONS)
    else:
        await channel.send(embed=embed, view=ProfileHubView(bot), allowed_mentions=NO_MENTIONS)

    print(f'Profile hub ready | guild={guild.id} | channel={channel.id}')
