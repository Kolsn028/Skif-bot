"""Одиночные записи с откатом; транзакции из нескольких запросов оформляются явно."""

import json
from datetime import datetime, timezone


class WriteRepository:
    async def _write(self, sql, params):
        async with self.lock:
            try:
                cursor = await self.conn.execute(sql, params)
                await self.conn.commit()
                return cursor.lastrowid
            except BaseException:
                await self.conn.rollback()
                raise

    async def record_audit(self, guild_id, actor_id, action, target_id, details):
        await self._write(
            'INSERT INTO audit_actions(guild_id,actor_id,action,target_id,details,created_at) VALUES (?,?,?,?,?,?)',
            (guild_id, actor_id, action, target_id, json.dumps(details, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
        )

    async def delete_event_signup(self, event_id, member_id):
        await self._write(
            'DELETE FROM event_signups WHERE event_id=? AND member_id=?',
            (event_id, member_id),
        )

    async def create_event_signup(self, event_id, member_id, seat):
        await self._write(
            'INSERT INTO event_signups(event_id,member_id,joined_at,seat) VALUES (?,?,?,?)',
            (event_id, member_id, datetime.now(timezone.utc).isoformat(), seat),
        )

    async def update_event_signup_seat(self, event_id, member_id, seat):
        await self._write(
            'UPDATE event_signups SET seat=? WHERE event_id=? AND member_id=?',
            (seat, event_id, member_id),
        )

    async def update_event_limits(self, event_id, capacity, reserve_capacity):
        await self._write(
            'UPDATE family_events SET capacity=?,reserve_capacity=? WHERE id=?',
            (capacity, reserve_capacity, event_id),
        )

    async def update_event_attendance(self, event_id, member_id, attended, confirmed_by):
        now = datetime.now(timezone.utc).isoformat()
        await self._write(
            'UPDATE event_signups SET attended=?,confirmed_by=?,confirmed_at=? WHERE event_id=? AND member_id=?',
            (attended, confirmed_by, now, event_id, member_id),
        )
