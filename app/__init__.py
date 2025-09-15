#!/usr/bin/env python3
"""
EmoJournal Telegram Bot
Emotion tracking with scientific approach and fixed scheduling
"""

__version__ = "1.0.0"
__author__ = "EmoJournal Team"
__description__ = "Telegram bot for emotion tracking and weekly insights"

# Make main modules easily importable
from .main import EmoJournalBot
from .db import Database, User, Entry, Schedule
from .scheduler import FixedScheduler
from .analysis import WeeklyAnalyzer
from .i18n import Texts

__all__ = [
    'EmoJournalBot',
    'Database',
    'User', 
    'Entry',
    'Schedule',
    'FixedScheduler',
    'WeeklyAnalyzer', 
    'Texts'
]
