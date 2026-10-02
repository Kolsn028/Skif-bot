"""Только политика прав: никаких сообщений в Discord, SQL и выдачи ролей."""

import os


def env_id(name):
    value = (os.getenv(name) or '').strip()
    return int(value) if value.isdigit() else 0


STAFF_KEYS = ('leader_role_id', 'dep_leader_role_id', 'high_staff_role_id', 'recruiter_role_id')
HIGH_KEYS = STAFF_KEYS[:3]
REPORT_KEYS = STAFF_KEYS
PROMOTION_KEYS = STAFF_KEYS
MANAGEMENT_KEYS = HIGH_KEYS


def has_role(member, cfg, keys):
    return any(cfg.get(k) and member.get_role(cfg[k]) for k in keys)


def is_leader(member, cfg):
    return member.id == member.guild.owner_id or has_role(member, cfg, ('leader_role_id',))


def may_recruit(member, cfg):
    return is_leader(member, cfg) or bool(has_role(member, cfg, STAFF_KEYS))


def may_review_reports(member, cfg):
    return is_leader(member, cfg) or bool(has_role(member, cfg, REPORT_KEYS))


def may_promote(member, cfg):
    return is_leader(member, cfg) or bool(has_role(member, cfg, PROMOTION_KEYS))


def may_manage_recruiters(member, cfg):
    return is_leader(member, cfg) or bool(has_role(member, cfg, MANAGEMENT_KEYS))


def may_review_vacation(member, cfg):
    return is_leader(member, cfg) or bool(has_role(member, cfg, MANAGEMENT_KEYS))


def is_family(member, cfg):
    return is_leader(member, cfg) or has_role(member, cfg, STAFF_KEYS + ('accepted_role_id', 'main_role_id', 'family_role_id'))


# У проверки тиров нет обхода для владельца, админа и старших ролей.
# Тиры работают на настроенном сервере; роль проверяющего выдаёт setup.
TIER_GUILD_ID = env_id('TIER_GUILD_ID') or env_id('GUILD_ID')
TIERCHECK_ROLE_ID = env_id('TIERCHECK_ROLE_ID')


def may_review_tiers(member, guild_id, cfg=None):
    if guild_id != TIER_GUILD_ID:
        return False
    role_id = TIERCHECK_ROLE_ID or (cfg or {}).get('tiercheck_role_id')
    return bool(role_id and member.get_role(role_id))


def may_manage_events(member, cfg):
    return may_manage_recruiters(member, cfg)


def may_find_rooms(member, cfg):
    """Поиск личного канала участника: Хай, Дэп Овнер и Овнер."""
    return may_manage_recruiters(member, cfg)


def may_view_profiles(member, cfg):
    return may_manage_recruiters(member, cfg)


def may_confirm_attendance(member, cfg, event):
    return (
        is_leader(member, cfg)
        or bool(has_role(member, cfg, ('dep_leader_role_id',)))
        or (member.id == event['creator_id'] and bool(has_role(member, cfg, HIGH_KEYS)))
    )


def may_use_legacy_admin(member, cfg):
    # Сохраняем существующее переопределение команды/назначения; Хай молча не расширяем.
    return is_leader(member, cfg) or has_role(member, cfg, ('dep_leader_role_id',)) or member.guild_permissions.administrator


def may_decide_application(member, cfg, application):
    return (
        may_recruit(member, cfg)
        and bool(application.get('assigned_to'))
        and (application['assigned_to'] == member.id or may_use_legacy_admin(member, cfg))
    )


def may_setup(member, cfg, resolve_role):
    """Только настроенная роль Овнер. Владелец сервера и администратор обходом не считаются."""
    leader_id = cfg.get('leader_role_id')
    if leader_id:
        return bool(member.get_role(leader_id))
    if not cfg.get('role_schema_version'):
        role = resolve_role(member.guild, 'leader_role_id')
        return bool(role and member.get_role(role.id))
    return False
