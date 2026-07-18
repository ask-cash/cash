"""
card_ui.py — Telegram glue for services.cards.

Turns a platform-agnostic ``Card`` into python-telegram-bot objects and
sends/edits it. Kept separate from services.cards so the card model stays
import-free and unit-testable; this is the only place cards meet PTB.
"""

from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from services import cards

logger = logging.getLogger(__name__)


def _markup(card: cards.Card):
    tg = cards.to_telegram(card)
    keyboard = tg["keyboard"]
    markup = None
    if keyboard:
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(b["text"], callback_data=b["callback_data"]) for b in row]
            for row in keyboard
        ])
    return tg["text"], markup


async def send_card(message, card: cards.Card):
    """Send ``card`` as a reply to a Telegram message."""
    text, markup = _markup(card)
    return await message.reply_text(text, reply_markup=markup)


async def edit_card(query, card: cards.Card):
    """Re-render ``card`` in place on a callback query's message."""
    text, markup = _markup(card)
    try:
        await query.edit_message_text(text, reply_markup=markup)
    except Exception:
        logger.exception("[card_ui] edit_message_text failed")
