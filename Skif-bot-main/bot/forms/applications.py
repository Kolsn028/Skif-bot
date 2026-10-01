from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
import discord
from ..theme import DANGER, SUCCESS, WARNING
from ..ui import base_embed
from ..recruiting import update_assignment_card, interview_room, set_card_status
from ..roles import notify_recruiters, application_recruiters
from ..interactions import SafeModal, SafeView, serialized, private_thread


def build_application_card(user, app_id, real_name_age, majestic_experience, shooting_skill, level_online_tz, family_experience):
    """Карточка анкеты в приватной ветке. Поля «Статус» и «Ответственный» обновляются по имени."""
    e = base_embed(f'📋 Заявка #{app_id}', f'{user.mention} • `{user.id}`\nПодана <t:{int(datetime.now(timezone.utc).timestamp())}:R>', WARNING)
    e.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    e.set_thumbnail(url=user.display_avatar.url)
    e.add_field(name='👤 Имя, возраст, ник', value=str(real_name_age)[:1024], inline=True)
    e.add_field(name='📊 LVL, онлайн, пояс', value=str(level_online_tz)[:1024], inline=True)
    e.add_field(name='🎯 Откат, стрельба', value=(str(shooting_skill) or 'Не указано')[:1024], inline=True)
    e.add_field(name='🎮 Опыт на Majestic', value=str(majestic_experience)[:1024], inline=False)
    e.add_field(name='🏠 Опыт в семьях', value=str(family_experience)[:1024], inline=False)
    e.add_field(name='Статус', value='🟡 На рассмотрении', inline=True)
    e.add_field(name='Ответственный', value='Свободна — нажми «Взять заявку»', inline=True)
    return e


class ApplicationModal(SafeModal, title='Заявка в SKIF Family'):
    real_name_age = discord.ui.TextInput(label='Имя, возраст и игровой ник', placeholder='Иван, 19 лет, Ivan_Skif', min_length=3, max_length=160)
    majestic_experience = discord.ui.TextInput(
        label='Опыт на Majestic', placeholder='Сколько играешь, на каком сервере, чем занимался', min_length=3, max_length=500
    )
    shooting_skill = discord.ui.TextInput(
        label='Откат или уровень стрельбы', placeholder='Ссылка на откат или уровень. Можно пропустить', required=False, max_length=300
    )
    level_online_tz = discord.ui.TextInput(
        label='LVL, онлайн и часовой пояс', placeholder='45 lvl, 5 часов в день, МСК+2', min_length=3, max_length=200
    )
    family_experience = discord.ui.TextInput(
        label='Опыт в семьях',
        placeholder='Где состоял, сколько времени, почему ушёл. Если не состоял, так и напиши',
        style=discord.TextStyle.paragraph,
        min_length=2,
        max_length=900,
    )

    def __init__(self, bot):
        super().__init__(timeout=300)
        self.bot = bot

    @serialized('application_submit', by_user=True)
    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        cfg = await self.bot.db.get_config(interaction.guild.id)
        parent = interaction.guild.get_channel(cfg.get('applications_parent_channel_id') or 0)
        log_ch = interaction.guild.get_channel(cfg.get('applications_log_channel_id') or 0)
        recruiter_role = interaction.guild.get_role(cfg.get('recruiter_role_id') or 0)
        if not isinstance(parent, discord.TextChannel) or not isinstance(log_ch, discord.TextChannel) or not recruiter_role:
            return await interaction.response.send_message('⚠️ Система заявок не настроена. Выполните `/setup`.', ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)
        existing = await self.bot.db.find_open_application(interaction.guild.id, interaction.user.id)
        if existing:
            return await interaction.followup.send(f'Твоя заявка уже рассматривается: <#{existing["thread_id"]}>.', ephemeral=True)
        now = self.bot.now_iso()
        app_id = await self.bot.db.create_application(
            guild_id=interaction.guild.id,
            applicant_id=interaction.user.id,
            applicant_tag=str(interaction.user),
            real_name_age=str(self.real_name_age),
            majestic_experience=str(self.majestic_experience),
            shooting_skill=str(self.shooting_skill) or 'Не указано',
            level_online_tz=str(self.level_online_tz),
            family_experience=str(self.family_experience),
            extra='',
            status='pending',
            created_at=now,
            updated_at=now,
        )

        if not interaction.guild.chunked:
            await interaction.guild.chunk(cache=True)
        try:
            thread = await private_thread(
                parent,
                interaction.user,
                [],
                f'заявка-{app_id}-{interaction.user.display_name}',
                reviewers=application_recruiters(interaction.guild, cfg),
            )
        except Exception:
            await self.bot.db.update_application(app_id, status='failed', updated_at=self.bot.now_iso())
            raise

        await self.bot.db.update_application(app_id, thread_id=thread.id)
        e = build_application_card(
            interaction.user, app_id, self.real_name_age, self.majestic_experience, self.shooting_skill, self.level_online_tz, self.family_experience
        )
        try:
            await thread.send(content=None, embed=e, view=RecruiterActionView(self.bot))
        except Exception:
            await self.bot.db.update_application(app_id, status='failed', updated_at=self.bot.now_iso())
            await thread.delete(reason='Skif: не удалось отправить анкету')
            raise

        await notify_recruiters(
            thread,
            interaction.guild,
            cfg,
            base_embed('📥 Новая заявка', f'Кандидат: {interaction.user.mention}\nРекруты, возьмите заявку в работу.', WARNING),
        )
        log = await log_ch.send(
            allowed_mentions=discord.AllowedMentions.none(),
            embed=base_embed(f'📥 Новая заявка #{app_id}', f'{interaction.user.mention}\nВетка: {thread.mention}'),
        )
        await self.bot.db.update_application(app_id, log_message_id=log.id)
        await interaction.followup.send(
            f'✅ Заявка **#{app_id}** отправлена. Рекрут ответит в твоей ветке: {thread.mention}. Её видишь только ты и рекруты.', ephemeral=True
        )


class ApplicationPanelView(SafeView):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label='Подать заявку', emoji='📝', style=discord.ButtonStyle.success, custom_id='skif:application:open')
    async def open_application(self, interaction: discord.Interaction, _button):
        await interaction.response.send_modal(ApplicationModal(self.bot))

    @discord.ui.button(label='Мои заявки', emoji='📬', style=discord.ButtonStyle.secondary, custom_id='skif:application:mine')
    async def mine(self, interaction, _button):
        from ..dashboard import open_requests

        await open_requests(self.bot, interaction, own=True)


class RecruiterActionSelect(discord.ui.Select):
    def __init__(self, bot):
        self.bot = bot
        super().__init__(
            placeholder='Решение по заявке…',
            min_values=1,
            max_values=1,
            custom_id='skif:recruiter:action',
            options=[
                discord.SelectOption(label='Принять кандидата', value='accept', emoji='✅', description='Выдать роль Academy и закрыть заявку'),
                discord.SelectOption(
                    label='Вызвать на обзвон', value='interview', emoji='📞', description='Пригласить в голосовой канал на 15 минут'
                ),
                discord.SelectOption(label='Отложить', value='hold', emoji='⏳', description='Оставить на рассмотрении'),
                discord.SelectOption(label='Отказать', value='reject', emoji='❌', description='Указать причину и закрыть заявку'),
            ],
        )

    @serialized('recruiter_decision')
    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        if not await self.bot.is_recruiter(interaction.user):
            return await interaction.response.send_message('⛔ Только для рекрутеров.', ephemeral=True)
        app = await self.bot.db.get_application_by_thread(interaction.guild.id, interaction.channel.id)
        if not app:
            return await interaction.response.send_message('Заявка не найдена.', ephemeral=True)

        if app['status'] in ('accepted', 'rejected'):
            return await interaction.response.send_message('Эта заявка уже закрыта.', ephemeral=True)
        if not app.get('assigned_to'):
            await interaction.response.send_message('Сначала нажми «Взять заявку».', ephemeral=True)
            await interaction.message.edit(view=RecruiterActionView(self.bot))
            return
        if app['assigned_to'] != interaction.user.id and not await self.bot.can_manage(interaction.user):
            return await interaction.response.send_message(
                f'Заявка закреплена за <@{app["assigned_to"]}>. Решение принимает ответственный рекрутер.', ephemeral=True
            )
        action = self.values[0]
        if action == 'reject':
            from ..enhancements import RejectionModal

            return await interaction.response.send_modal(RejectionModal(self.bot, app['id']))
        await interaction.response.defer(ephemeral=True, thinking=True)
        cfg = await self.bot.db.get_config(interaction.guild.id)
        applicant = interaction.guild.get_member(app['applicant_id'])

        if action == 'interview':
            text_ch = interaction.guild.get_channel(cfg.get('interview_channel_id') or 0)
            if not isinstance(text_ch, discord.TextChannel):
                return await interaction.followup.send('⚠️ Канал обзвона не настроен.', ephemeral=True)
            voice_ch = await interview_room(self.bot, interaction.guild, cfg, app)
            if not voice_ch:
                return await interaction.followup.send(
                    'Все каналы обзвона заняты, зарезервированы или недоступны кандидату. Повтори вызов позже; для создания трёх каналов используй /setup.',
                    ephemeral=True,
                )
            try:
                await text_ch.send(
                    embed=base_embed(
                        f'📞 Вызов на обзвон • заявка #{app["id"]}',
                        f'Кандидат: <@{app["applicant_id"]}>\nОтветственный: <@{app["assigned_to"]}>\nГолосовой: {voice_ch.mention}\nКанал зарезервирован на 15 минут.',
                        0x5865F2,
                    ),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.DiscordException:
                await self.bot.db.clear_interview(app['id'], self.bot.now_iso())
                raise
            if (
                os.getenv('MOVE_TO_INTERVIEW_VOICE', 'false').lower() == 'true'
                and applicant
                and applicant.voice
                and isinstance(voice_ch, discord.VoiceChannel)
            ):
                try:
                    await applicant.move_to(voice_ch)
                except discord.DiscordException:
                    pass
            if applicant:
                try:
                    await applicant.send(
                        embed=base_embed(
                            'Приглашение на обзвон • Skif',
                            f'Твоя заявка принята на следующий этап.\nКанал беседы: {voice_ch.mention if voice_ch else text_ch.mention}\nВетка: {interaction.channel.jump_url}',
                        )
                    )
                except discord.Forbidden:
                    pass
            await set_card_status(getattr(interaction, 'message', None), '📞 На обзвоне')
            return await interaction.followup.send(f'📞 Вызов отправлен. Канал: {voice_ch.mention}, резерв — 15 минут.', ephemeral=True)

        if action == 'hold':
            await self.bot.db.update_application(
                app['id'],
                status='pending',
                interview_room_id=None,
                interview_until=None,
                handled_by=interaction.user.id,
                updated_at=self.bot.now_iso(),
            )
            await set_card_status(getattr(interaction, 'message', None), '⏳ Отложена')
            await interaction.followup.send('⏳ Оставлено на рассмотрении.', ephemeral=True)
            return

        if app['status'] in ('accepted', 'rejected'):
            return await interaction.followup.send('Эта заявка уже закрыта.', ephemeral=True)

        accepted = action == 'accept'
        color = SUCCESS if accepted else DANGER
        title = '✅ Кандидат принят' if accepted else '❌ По заявке отказ'
        from ..services.applications import decide, ApplicationDecisionError

        try:
            await decide(self.bot, interaction.guild, interaction.user, interaction.channel.id, accepted=accepted, expected_id=app['id'])
        except ApplicationDecisionError as exc:
            return await interaction.followup.send(str(exc), ephemeral=True)

        await interaction.followup.send('✅ Решение сохранено.', ephemeral=True)
        await set_card_status(getattr(interaction, 'message', None), '✅ Принят' if accepted else '❌ Отказано', color)
        await interaction.channel.send(embed=base_embed(title, f'Рекрутер: {interaction.user.mention}\nКандидат: <@{app["applicant_id"]}>', color))
        if accepted:
            log_ch = interaction.guild.get_channel(cfg.get('applications_log_channel_id') or 0)
            if isinstance(log_ch, discord.TextChannel):
                await notify_recruiters(
                    log_ch,
                    interaction.guild,
                    cfg,
                    base_embed(
                        f'Принят • заявка #{app["id"]}',
                        f'Кандидат: <@{app["applicant_id"]}>\nРанг: **Academy**\nРешение: {interaction.user.display_name}',
                        SUCCESS,
                    ),
                )
        await self.bot.send_or_update_leaderboard(interaction.guild)

        await asyncio.sleep(5)
        if isinstance(interaction.channel, discord.Thread):
            try:
                await interaction.channel.edit(archived=True, locked=True)
            except discord.DiscordException:
                pass


class RecruiterActionView(SafeView):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.add_item(RecruiterActionSelect(bot))

    @discord.ui.button(label='Взять заявку', emoji='🙋', style=discord.ButtonStyle.primary, custom_id='skif:recruiter:claim', row=1)
    @serialized('recruiter_decision')
    async def claim(self, interaction, _button):
        if not isinstance(interaction.user, discord.Member) or not await self.bot.is_recruiter(interaction.user):
            return await interaction.response.send_message('Только Рекрут и руководство.', ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        app = await self.bot.db.get_application_by_thread(interaction.guild.id, interaction.channel.id)
        if not app or app['status'] not in ('pending', 'interview'):
            return await interaction.followup.send('Заявка уже закрыта или не найдена.', ephemeral=True)
        claimed = await self.bot.db.claim_application(app['id'], interaction.user.id, self.bot.now_iso())
        current = await self.bot.db.get_application_by_thread(interaction.guild.id, interaction.channel.id)
        from ..membership import sync_application_members

        await sync_application_members(self.bot, interaction.channel, current)
        await update_assignment_card(interaction.message, current['assigned_to'])
        if not claimed:
            return await interaction.followup.send(f'Ответственный уже назначен: <@{current["assigned_to"]}>.', ephemeral=True)
        await interaction.followup.send('Заявка закреплена за тобой. Теперь доступны вызов, приём и отказ.', ephemeral=True)

    @discord.ui.button(label='Освободить заявку', emoji='↩️', style=discord.ButtonStyle.secondary, custom_id='skif:recruiter:release', row=1)
    @serialized('recruiter_decision')
    async def release(self, interaction, _button):
        if not isinstance(interaction.user, discord.Member) or not await self.bot.is_recruiter(interaction.user):
            return await interaction.response.send_message('Только Рекрут и руководство.', ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        app = await self.bot.db.get_application_by_thread(interaction.guild.id, interaction.channel.id)
        if not app or app['status'] not in ('pending', 'interview'):
            return await interaction.followup.send('Заявка уже закрыта или не найдена.', ephemeral=True)
        if app.get('assigned_to') != interaction.user.id and not await self.bot.can_manage(interaction.user):
            return await interaction.followup.send('Освободить заявку может ответственный рекрутер.', ephemeral=True)
        await self.bot.db.release_application(app['id'], self.bot.now_iso())
        from ..membership import sync_application_members

        await sync_application_members(self.bot, interaction.channel, {**app, 'assigned_to': None})
        await update_assignment_card(interaction.message, None)
        await interaction.followup.send('Заявка свободна. Резерв голосового канала снят.', ephemeral=True)
