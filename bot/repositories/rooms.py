"""SQL для личных каналов участников (member_rooms)."""

import json


class RoomsRepository:
    async def get_room(self, guild_id, member_id):
        row = await self._one('SELECT * FROM member_rooms WHERE guild_id=? AND member_id=?', (guild_id, member_id))
        if row:
            row['threads'] = json.loads(row['threads'] or '{}')
        return row

    async def save_room(self, guild_id, member_id, channel_id, threads, now_iso):
        await self._write(
            'INSERT INTO member_rooms(guild_id,member_id,channel_id,threads,created_at) VALUES (?,?,?,?,?) '
            'ON CONFLICT(guild_id,member_id) DO UPDATE SET channel_id=excluded.channel_id, threads=excluded.threads',
            (guild_id, member_id, channel_id, json.dumps(threads, sort_keys=True), now_iso),
        )
