"""All roster mutations use the database lock; counters never exceed seat limits."""
import json
from datetime import datetime, timezone
from .access import may_confirm_attendance as may_confirm




async def audit(db,guild_id,actor,action,target,details):
    await db.record_audit(guild_id, actor, action, target, details)


async def join(db,event_id,member_id,leave=False,seat='main'):
    if seat not in ('main','reserve'):raise ValueError('Неизвестный состав.')
    async with db.lock:
        event=await db._one('SELECT * FROM family_events WHERE id=?',(event_id,))
        if not event or event['status']!='open':return 'Сбор завершён.'
        current=await db._one('SELECT * FROM event_signups WHERE event_id=? AND member_id=?',(event_id,member_id))
        if leave:
            if current and current['attended']:return 'Присутствие уже подтверждено. Изменение — через организатора.'
            await db.delete_event_signup(event_id, member_id)
            return 'Ты вышел из списка.'
        if current:return 'Ты уже записан.'
        cap=event['capacity'] if seat=='main' else event['reserve_capacity']
        count=await db._one('SELECT COUNT(*) n FROM event_signups WHERE event_id=? AND seat=?',(event_id,seat))
        if count['n']>=cap:return 'Основа заполнена — нажми «В резерв».' if seat=='main' else 'Резерв заполнен. Дождись свободного места или обратись к организатору.'
        await db.create_event_signup(event_id, member_id, seat)
        return 'Ты записан!' if seat=='main' else 'Ты записан в резерв!'


async def move(db,event_id,member_id,seat,actor):
    if seat not in ('main','reserve'):raise ValueError('Неизвестный состав.')
    async with db.lock:
        event=await db._one('SELECT * FROM family_events WHERE id=?',(event_id,))
        if not event or event['status']!='open':raise ValueError('Сбор уже завершён.')
        row=await db._one('SELECT * FROM event_signups WHERE event_id=? AND member_id=?',(event_id,member_id))
        if not row:raise ValueError('Участник не записан.')
        if row['seat']==seat:return
        cap=event['capacity'] if seat=='main' else event['reserve_capacity']
        count=await db._one('SELECT COUNT(*) n FROM event_signups WHERE event_id=? AND seat=?',(event_id,seat))
        if count['n']>=cap:raise ValueError('В выбранном составе нет свободных мест. Сначала измени лимит или освободи место.')
        await db.update_event_signup_seat(event_id, member_id, seat)
        await db.record_audit(event['guild_id'], actor, 'seat', member_id, {'event': event_id, 'from': row['seat'], 'to': seat})


async def limits(db,event_id,main,reserve,actor):
    if not 1<=main<=100 or not 0<=reserve<=99 or main+reserve>100:
        raise ValueError('Основа: 1–100, резерв: 0–99, всего не больше 100 мест.')
    async with db.lock:
        event=await db._one('SELECT * FROM family_events WHERE id=?',(event_id,))
        if not event or event['status']!='open':raise ValueError('Сбор завершён.')
        rows=await db._all('SELECT seat,COUNT(*) n FROM event_signups WHERE event_id=? GROUP BY seat',(event_id,))
        if any(r['n'] > (main if r['seat']=='main' else reserve) for r in rows):
            raise ValueError('Новый лимит меньше числа записанных. Сначала перемести участников.')
        await db.update_event_limits(event_id, main, reserve)
        await db.record_audit(event['guild_id'], actor, 'limits', event_id, {'main': main, 'reserve': reserve})


async def confirm(db,event_id,member_id,actor):
    async with db.lock:
        event=await db._one('SELECT * FROM family_events WHERE id=?',(event_id,))
        if not event or event['starts_at']>datetime.now(timezone.utc).timestamp():
            raise ValueError('Подтверждать присутствие можно после начала МП.')
        row=await db._one('SELECT * FROM event_signups WHERE event_id=? AND member_id=?',(event_id,member_id))
        if not row:raise ValueError('Этот участник не записан.')
        value=1-row['attended']
        await db.update_event_attendance(event_id, member_id, value, actor)
        await db.record_audit(event['guild_id'], actor, 'attendance', member_id, {'event': event_id, 'confirmed': value})

