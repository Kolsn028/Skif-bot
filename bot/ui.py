import os
from pathlib import Path
from datetime import datetime, timezone
import discord

FAMILY_NAME = os.getenv('FAMILY_NAME', 'SKIF FAMILY')
try:
    EMBED_COLOR = int(os.getenv('EMBED_COLOR', '0xA82D40'), 16)
except ValueError:
    EMBED_COLOR = 0xA82D40
BANNER_URL = os.getenv('BANNER_URL', '').strip()
FOOTER_TEXT = os.getenv('FOOTER_TEXT', 'SKIF Family')


def base_embed(title, description='', color=None):
    e = discord.Embed(title=title, description=description, color=color if color is not None else EMBED_COLOR, timestamp=datetime.now(timezone.utc))
    e.set_author(name=FAMILY_NAME)
    e.set_footer(text=FOOTER_TEXT)
    return e


def panel(title, description, fields, color=EMBED_COLOR):
    e = base_embed(title, description, color)
    for name, value in fields:
        e.add_field(name=name, value=value, inline=False)
    if BANNER_URL.startswith('https://'):
        e.set_image(url=BANNER_URL)
    return e


def application_banner_file():
    return discord.File(Path(__file__).resolve().parent.parent / 'assets' / 'skif-banner.png', filename='skif-banner.png')


def application_panel_embed():
    e = base_embed(
        'Подать заявку',
        'Заполни короткую анкету — рекрутер рассмотрит её в приватной ветке.\n'
        'После принятия получишь роль **Academy**.\n\n'
        '**Готов? Нажми «Подать заявку».**',
    )
    e.set_image(url='attachment://skif-banner.png')
    return e


def vacation_panel_embed():
    return panel(
        'ВРЕМЯ НА ОТДЫХ',
        'Нужна пауза? Предупреди руководство — сохрани порядок в составе.',
        [
            ('01  /  ОСТАВЬ ЗАЯВКУ', 'Укажи причину и срок: **от 1 до 60 дней**.'),
            ('02  /  ДОЖДИСЬ РЕШЕНИЯ', 'Бот создаст отдельную приватную ветку для тебя и руководства.'),
            (
                '03  /  ВОЗВРАЩАЙСЯ В СТРОЙ',
                'Добавляется только роль Отдых. Остальные роли сохраняются. Для возврата нажми «Вернуться из отпуска»: причина и комментарий, затем одобрение Хай и выше.',
            ),
        ],
        0xC69B59,
    )


def activity_type_label(value):
    return {
        'capt': '⚔️ Капт',
        'mp': '🎯 МП',
        'msh': '🛡️ МШ',
        'training': '🏋️ Тренировка',
        'mcl': '🟥 MCL',
        'vzm': '🟩 VZM',
        'vzz': '🟦 VZZ',
        'contract': '🟠 Контракт',
        'other': '📌 Другое',
        'unclassified': '❔ Не выбран',
    }.get(value, value)
