from __future__ import annotations
from .access import may_use_legacy_admin
from .timeutil import msk_today
import os
import asyncio
import logging
from collections import OrderedDict
from datetime import date, datetime, timezone
from aiohttp import web
import discord
from .performance import edit_if_changed, coalesced_panel
from discord.ext import commands, tasks
from .ui import base_embed

log = logging.getLogger(__name__)
from .roles import is_family, may_recruit, may_review_reports, may_promote, may_review_vacation, may_manage_recruiters


class _OperationLocks:
    """Bounded registry of per-operation asyncio locks (LRU eviction)."""

    def __init__(self, max_entries: int):
        self._max_entries = max_entries
        self._locks: OrderedDict[object, asyncio.Lock] = OrderedDict()

    def __getitem__(self, key: object) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
            while len(self._locks) > self._max_entries:
                for existing_key, existing_lock in self._locks.items():
                    if not existing_lock.locked():
                        del self._locks[existing_key]
                        break
                else:
                    break
        else:
            self._locks.move_to_end(key)
        return lock


class SkifBot(commands.Bot):
    def __init__(self, *args, db, **kwargs):
        super().__init__(*args, **kwargs)
        self.db = db
        self.health_runner = None
        self.operation_locks = _OperationLocks(max_entries=2048)

    def now_iso(self):
        return datetime.now(timezone.utc).isoformat()

    async def setup_hook(self):
        await self.db.connect()
        from .discord_backup import DiscordBackups

        self.backups = DiscordBackups(self)
        await self.backups.restore()
        from .tiers import TierPanelView, TierReviewView

        self.add_view(TierPanelView(self))
        self.add_view(TierReviewView(self))
        from .dashboard import ManagementView

        self.add_view(ManagementView(self))
        from .views import (
            ApplicationPanelView,
            RecruiterActionView,
            VacationPanelView,
            VacationDecisionView,
            ActivityClassifyView,
            ActivityReviewView,
        )

        for view in (
            ApplicationPanelView(self),
            RecruiterActionView(self),
            VacationPanelView(self),
            VacationDecisionView(self),
            ActivityClassifyView(self),
            ActivityReviewView(self),
        ):
            self.add_view(view)
        from .progression import (
            ContractPanelView,
            GreenPanelView,
            ProgressReviewView,
            PromotionPanelView,
            WarnPanelView,
        )

        for view in (
            ContractPanelView(self),
            GreenPanelView(self),
            WarnPanelView(self),
            PromotionPanelView(self),
            ProgressReviewView(self),
        ):
            self.add_view(view)
        from .profiles import ProfileLauncher

        self.add_view(ProfileLauncher(self))
        from .leave import ReturnDecisionView

        self.add_view(ReturnDecisionView(self))
        from .events import EventPanelView, EventView

        self.add_view(EventPanelView(self))
        self.add_view(EventView(self, legacy=True))
        gid = int(os.getenv('GUILD_ID')) if os.getenv('GUILD_ID') else None
        try:
            if gid:
                g = discord.Object(id=gid)
                self.tree.copy_global_to(guild=g)
                await self.tree.sync(guild=g)
            else:
                await self.tree.sync()
        except Exception:
            log.exception('Slash sync failed')
        await self._start_health()
        self.housekeeping.start()
        self.application_reminders.start()
        self.backups.watch_commits()

    async def _start_health(self):
        async def health(_):
            return web.json_response({'ok': True})

        app = web.Application()
        app.router.add_get('/', health)
        app.router.add_get('/health', health)
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, '0.0.0.0', int(os.getenv('PORT', '8080'))).start()
        self.health_runner = runner

    async def close(self):
        if self.application_reminders.is_running():
            self.application_reminders.cancel()
        if self.housekeeping.is_running():
            self.housekeeping.cancel()
        if self.health_runner:
            await self.health_runner.cleanup()
        running = [s['task'] for s in getattr(self, '_panel_tasks', {}).values()] + list(getattr(self, '_tier_sync_tasks', {}).values())
        if running:
            await asyncio.gather(*running, return_exceptions=True)
        if hasattr(self, 'backups'):
            await self.backups.close()
        await self.db.close()
        await super().close()

    async def on_ready(self):
        await self.change_presence(activity=discord.Game(name='Skif • заявки и МП'))
        log.info('Skif online | user=%s | guilds=%s', self.user, len(self.guilds))
        for guild in self.guilds:
            await self.sync_guild_commands(guild)
        if getattr(self, '_layout_attempted', False):
            return
        self._layout_attempted = True
        from .tiers import install as install_tiers

        for guild in self.guilds:
            try:
                await install_tiers(self, guild)
            except Exception as exc:
                log.error('Tier setup failed | guild=%s: %s', guild.id, exc, exc_info=True)
        from .enhancements import refresh_interface

        for guild in self.guilds:
            try:
                await refresh_interface(self, guild)
            except Exception as exc:
                log.error('Interface refresh failed | guild=%s: %s', guild.id, exc, exc_info=True)
        for guild in self.guilds:
            cfg = await self.db.get_config(guild.id)
            if cfg.get('management_category_id'):
                try:
                    await self.backups.save(guild)
                except Exception as exc:
                    self.backups.errors[guild.id] = str(exc)
                    log.error('Discord backup initial save failed | guild=%s: %s', guild.id, exc, exc_info=True)

    async def _auto_provision(self, guild):
        """Создать роли, каналы и панели без /setup и сохранить их ID в конфиг.

        Пропускает уже настроенные серверы (server_layout_version == 10) и серверы,
        где боту не хватает прав — provision сам поднимет ValueError, а ручной /setup
        после выдачи прав достроит структуру, ничего не удаляя.
        """
        cfg = await self.db.get_config(guild.id)
        if cfg.get('server_layout_version') == 10:
            return
        from .provisioning import provision

        try:
            result = await provision(self, guild, {})
            issues = [f.value for f in result.fields if f.name == 'Проверь']
            log.info('Skif layout v10 ready | guild=%s | warnings=%s', guild.id, issues)
        except Exception as exc:
            import traceback

            traceback.print_exc()
            log.warning('Skif layout migration incomplete | guild=%s | error=%s: %s', guild.id, type(exc).__name__, exc, exc_info=True)

    async def sync_guild_commands(self, guild):
        async with self.operation_locks[('commands', guild.id)]:
            synced = getattr(self, '_commands_synced', set())
            if guild.id in synced:
                return
            try:
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                synced.add(guild.id)
                self._commands_synced = synced
            except Exception:
                log.exception('Guild slash sync failed | guild=%s', guild.id)

    async def on_guild_join(self, guild):
        await self.sync_guild_commands(guild)
        await self._auto_provision(guild)

    async def on_member_join(self, member):
        if member.bot:
            return
        cfg = await self.db.get_config(member.guild.id)
        role = member.guild.get_role(cfg.get('guest_role_id') or 0)
        if role:
            try:
                await member.add_roles(role, reason='Skif: вход на сервер')
            except discord.Forbidden:
                log.warning('Skif autorole: проверь Manage Roles и положение роли бота')

    async def on_member_update(self, before, after):
        from .tiers import GUILD_ID, TIERCHECK_ROLE_ID, sync_reviewers

        if not TIERCHECK_ROLE_ID:
            return
        if after.guild.id == GUILD_ID and not after.bot and after.get_role(TIERCHECK_ROLE_ID) and not before.get_role(TIERCHECK_ROLE_ID):
            await sync_reviewers(self, after.guild, after)

    async def can_manage(self, member):
        cfg = await self.db.get_config(member.guild.id)
        return may_use_legacy_admin(member, cfg)

    async def is_recruiter(self, member):
        return may_recruit(member, await self.db.get_config(member.guild.id))

    async def is_high_staff(self, member):
        return may_review_reports(member, await self.db.get_config(member.guild.id))

    async def is_family_member(self, member):
        return is_family(member, await self.db.get_config(member.guild.id))

    async def can_review_vacation(self, member):
        cfg = await self.db.get_config(member.guild.id)
        return may_review_vacation(member, cfg)

    async def can_promote(self, member):
        return may_promote(member, await self.db.get_config(member.guild.id))

    async def can_assign_recruiter(self, member):
        return may_manage_recruiters(member, await self.db.get_config(member.guild.id))

    def activity_points(self, cat):
        return {
            'capt': int(os.getenv('CAPT_POINTS', '3')),
            'mp': int(os.getenv('MP_POINTS', '2')),
            'msh': int(os.getenv('MSH_POINTS', '2')),
            'training': int(os.getenv('TRAINING_POINTS', '1')),
            'other': int(os.getenv('OTHER_POINTS', '1')),
            'mcl': 2,
            'vzm': 2,
            'vzz': 2,
            'contract': 1,
        }.get(cat, 0)

    async def on_message(self, msg):
        from .enhancements import mark_staff_response

        await mark_staff_response(self, msg)

    @coalesced_panel
    async def send_or_update_leaderboard(self, guild):
        c = await self.db.get_config(guild.id)
        rows = await self.db.leaderboard(guild.id, 10)
        medals = ['🥇', '🥈', '🥉']
        lines = []
        for i, r in enumerate(rows):
            lines.append(
                f'{medals[i] if i < 3 else f"`#{i + 1}`"} <@{r["recruiter_id"]}> — **{r["accepted_count"]}** принято'
                + (f' · {r["rejected_count"]} отказов' if r['rejected_count'] else '')
            )
        e = base_embed('🏆 Лидерборд рекрутеров', '\n'.join(lines) if lines else 'Пока нет данных.', 0xE5B64B)
        ch = guild.get_channel(c.get('leaderboard_channel_id') or 0)
        if not isinstance(ch, discord.TextChannel):
            return None
        mid = c.get('leaderboard_message_id')
        if mid:
            try:
                m = await ch.fetch_message(mid)
                await edit_if_changed(m, embed=e)
                return m
            except discord.NotFound:
                pass
        m = await ch.send(embed=e)
        await self.db.set_config(guild.id, leaderboard_message_id=m.id)
        return m

    @coalesced_panel
    async def update_vacation_status(self, guild):
        c = await self.db.get_config(guild.id)
        rows = await self.db.active_vacations(guild.id)
        today = msk_today()
        lines = []
        for r in rows:
            end = date.fromisoformat(r['end_date'])
            lines.append(f'🌴 <@{r["member_id"]}> — до **{end.strftime("%d.%m.%Y")}** · **{max((end - today).days, 0)} дн.** · возврат по заявке')
        e = base_embed('🌴 Кто сейчас в отпуске', '\n'.join(lines) if lines else 'Сейчас активных отпусков нет.', 0x3BAA72)
        ch = guild.get_channel(c.get('vacation_status_channel_id') or 0)
        if not isinstance(ch, discord.TextChannel):
            return None
        mid = c.get('vacation_status_message_id')
        if mid:
            try:
                m = await ch.fetch_message(mid)
                await edit_if_changed(m, embed=e)
                return m
            except discord.NotFound:
                pass
        m = await ch.send(embed=e)
        await self.db.set_config(guild.id, vacation_status_message_id=m.id)
        return m

    async def inactive_members(self, guild, days):
        rows = await self.db.last_activity_for_cases(guild.id)
        vacations = {x['member_id'] for x in await self.db.active_vacations(guild.id)}
        now = datetime.now(timezone.utc)
        out = []
        for r in rows:
            if r['member_id'] in vacations:
                continue
            m = guild.get_member(r['member_id'])
            if not m:
                continue
            raw = r['last_activity'] or r['case_created_at']
            dt = datetime.fromisoformat(raw)
            dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            d = int((now - dt).total_seconds() / 86400)
            if d >= days:
                out.append((m, d, r['last_activity']))
        return sorted(out, key=lambda x: x[1], reverse=True)

    @coalesced_panel
    async def update_inactivity_report(self, guild):
        c = await self.db.get_config(guild.id)
        days = int(os.getenv('INACTIVITY_DAYS_DEFAULT', '3'))
        rows = await self.inactive_members(guild, days)
        lines = [f'⚠️ {m.mention} — **{d} дн.**' for m, d, _ in rows[:30]]
        e = base_embed(
            f'📉 Контроль неактива • {days}+ дней',
            '\n'.join(lines) if lines else '✅ Участников с таким неактивом нет.',
            0xD64045 if lines else 0x3BAA72,
        )
        e.set_footer(text='Одобренный отпуск автоматически исключает участника из неактива.')
        ch = guild.get_channel(c.get('inactivity_report_channel_id') or 0)
        if not isinstance(ch, discord.TextChannel):
            return None
        mid = c.get('inactivity_report_message_id')
        if mid:
            try:
                m = await ch.fetch_message(mid)
                await edit_if_changed(m, embed=e)
                return m
            except discord.NotFound:
                pass
        m = await ch.send(embed=e)
        await self.db.set_config(guild.id, inactivity_report_message_id=m.id)
        return m

    async def expire_vacations(self, guild):
        # The date is informational: only an approved return restores roles.
        await self.update_vacation_status(guild)

    @tasks.loop(hours=1)
    async def housekeeping(self):
        for g in self.guilds:
            try:
                await self.expire_vacations(g)
                await self.update_inactivity_report(g)
            except Exception:
                log.exception('Housekeeping failed | guild=%s', g.id)

    @housekeeping.before_loop
    async def before_housekeeping(self):
        await self.wait_until_ready()

    @tasks.loop(minutes=5)
    async def application_reminders(self):
        from .enhancements import remind_applications

        for guild in self.guilds:
            try:
                await remind_applications(self, guild)
            except Exception as exc:
                log.error('Application reminders failed | guild=%s: %s', guild.id, exc, exc_info=True)

    @application_reminders.before_loop
    async def before_application_reminders(self):
        await self.wait_until_ready()
