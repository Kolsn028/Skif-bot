"""Решения по анкетам: проверка прав, смена ролей, затем одна атомарная запись результата.

Callbacks интерфейса могут держать свою блокировку recruiter_decision, а сервис берёт
собственную, чтобы одобрение и отказ шли по очереди и вне view. Сообщений он не
отправляет: сбой уведомления не отменяет уже записанное решение.
"""

import discord

from ..access import may_decide_application
from ..membership import accept_member


class ApplicationDecisionError(ValueError):
    """Решение принять нельзя; текст безопасно показать руководству."""


async def decide(bot, guild, actor, thread_id, *, accepted, reason=None, expected_id=None):
    if actor.guild.id != guild.id:
        raise ApplicationDecisionError('Участник находится на другом сервере.')
    async with bot.operation_locks[('application_action', guild.id, thread_id)]:
        app = await bot.db.get_application_by_thread(guild.id, thread_id)
        if not app or (expected_id is not None and app['id'] != expected_id):
            raise ApplicationDecisionError('Заявка изменилась. Открой её заново.')
        if app['status'] not in ('pending', 'interview'):
            raise ApplicationDecisionError('Заявка уже закрыта.')
        cfg = await bot.db.get_config(guild.id)
        if not may_decide_application(actor, cfg, app):
            raise ApplicationDecisionError('Решение принимает ответственный рекрутер или руководитель с правом управления заявкой.')
        if not accepted and len((reason or '').strip()) < 3:
            raise ApplicationDecisionError('Напиши причину отказа не короче трёх символов.')
        if accepted:
            applicant = guild.get_member(app['applicant_id'])
            if not applicant:
                raise ApplicationDecisionError('Участник вышел с сервера. Решение не сохранено.')
            try:
                await accept_member(applicant, cfg, f'Заявка #{app["id"]}: принят в Skif')
            except (discord.DiscordException, ValueError) as exc:
                raise ApplicationDecisionError(
                    'Не удалось завершить выдачу Skif + Academy и снятие Гость. Проверь роли и права бота, затем повтори приём. ' + str(exc)
                ) from exc
        status = 'accepted' if accepted else 'rejected'
        saved = await bot.db.record_application_decision(app['id'], guild.id, actor.id, status, bot.now_iso(), reason)
        if not saved:
            raise ApplicationDecisionError('Решение уже сохранено.')
        return {**app, 'status': status, 'handled_by': actor.id, 'rejection_reason': reason}
