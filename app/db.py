#!/usr/bin/env python3
"""
Database models and access layer for EmoJournal Bot
SQLite with SQLAlchemy for persistence - Enhanced with comprehensive user settings
"""

import os
import logging
from datetime import datetime, timezone as dt_timezone, date
from typing import Optional, List, Dict, Any
import json

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, Date, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.sql import func
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from .security import sanitize_user_input

logger = logging.getLogger(__name__)

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, unique=True, nullable=False, index=True)
    timezone = Column(String(50), default='Europe/Moscow', nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    paused = Column(Boolean, default=False, nullable=False)
    last_activity = Column(DateTime(timezone=True), default=func.now(), nullable=False)

class Entry(Base):
    __tablename__ = 'entries'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    ts_local = Column(DateTime, nullable=False, index=True)  # Local timezone timestamp
    valence = Column(Integer, nullable=True)  # -5 to +5 (Russell's Circumplex)
    arousal = Column(Integer, nullable=True)  # -5 to +5 (Russell's Circumplex) 
    emotions = Column(Text, nullable=True)  # JSON array of emotion words
    cause = Column(Text, nullable=True)  # What caused this emotion
    body = Column(Text, nullable=True)  # Bodily sensations
    note = Column(Text, nullable=True)  # Additional notes
    tags = Column(Text, nullable=True)  # JSON array of tags
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)

class Schedule(Base):
    __tablename__ = 'schedules'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    date_local = Column(Date, nullable=False, index=True)  # Local date
    times_local = Column(Text, nullable=False)  # JSON array of HH:MM strings
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)

class UserSettings(Base):
    __tablename__ = 'user_settings'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True, nullable=False, index=True)
    
    # Weekly summary settings
    weekly_summary_enabled = Column(Boolean, default=True, nullable=False)
    summary_time_hour = Column(Integer, default=21, nullable=False)  # Hour 0-23
    
    # Notification preferences
    ping_frequency = Column(String(20), default='normal', nullable=False)  # 'normal', 'reduced', 'minimal'
    weekend_pings = Column(Boolean, default=True, nullable=False)  # Ping on weekends
    
    # Privacy settings
    data_retention_days = Column(Integer, default=365, nullable=False)  # How long to keep data
    
    # Display preferences
    preferred_language = Column(String(10), default='ru', nullable=False)
    emoji_style = Column(String(20), default='default', nullable=False)  # 'default', 'minimal', 'colorful'
    
    # Advanced settings (JSON for extensibility)
    advanced_settings = Column(Text, nullable=True)  # JSON for future features
    
    # Metadata
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)

# NEW: Summary delivery tracking
class SummaryDelivery(Base):
    __tablename__ = 'summary_deliveries'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    delivery_date = Column(Date, nullable=False, index=True)  # Date when summary was sent
    summary_period_days = Column(Integer, default=7, nullable=False)  # Period covered (7, 14, 30, etc.)
    delivery_type = Column(String(20), default='automatic', nullable=False)  # 'automatic', 'manual'
    entries_count = Column(Integer, default=0, nullable=False)  # Number of entries included
    success = Column(Boolean, default=True, nullable=False)  # Whether delivery succeeded
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)

# Create indexes for performance
Index('idx_entries_user_date', Entry.user_id, Entry.ts_local)
Index('idx_schedules_user_date', Schedule.user_id, Schedule.date_local)
Index('idx_user_settings_user_id', UserSettings.user_id)
Index('idx_summary_deliveries_user_date', SummaryDelivery.user_id, SummaryDelivery.delivery_date)

class Database:
    """Database access layer with enhanced user settings and summary tracking"""
    
    def __init__(self, db_url: Optional[str] = None):
        if db_url is None:
            db_url = os.getenv('DATABASE_URL', 'sqlite:///data/emojournal.db')
        
        # Ensure data directory exists for SQLite
        if db_url.startswith('sqlite:///'):
            db_path = db_url.replace('sqlite:///', '')
            os.makedirs(os.path.dirname(db_path) or '.', exist_ok=True)
            self.db_path = db_path
        else:
            self.db_path = None
        
        self.engine = create_engine(
            db_url,
            echo=False,  # Set to True for SQL debugging
            pool_pre_ping=True,
            connect_args={"check_same_thread": False} if db_url.startswith('sqlite') else {}
        )
        
        # Create tables
        Base.metadata.create_all(self.engine)
        
        # Create session factory
        self.SessionLocal = sessionmaker(bind=self.engine)
        
        logger.info(f"Database initialized: {db_url}")
    
    def get_session(self) -> Session:
        """Get database session"""
        return self.SessionLocal()
    
    def create_user(self, user_id: int, chat_id: int, user_timezone: str = 'Europe/Moscow') -> User:
        """Create new user with validation and comprehensive default settings"""
        # Validate inputs
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("Invalid user_id")
        if not isinstance(chat_id, int) or chat_id <= 0:
            raise ValueError("Invalid chat_id")
        
        # Validate timezone
        timezone_validated = sanitize_user_input(user_timezone, "general")
        if not timezone_validated:
            timezone_validated = 'Europe/Moscow'
        
        # Validate timezone format
        try:
            import zoneinfo
            zoneinfo.ZoneInfo(timezone_validated)
        except Exception:
            timezone_validated = 'Europe/Moscow'
        
        try:
            with self.get_session() as session:
                # Check if user already exists
                existing_user = session.query(User).filter(User.id == user_id).first()
                if existing_user:
                    logger.warning(f"User {user_id} already exists")
                    return existing_user
                
                user = User(
                    id=user_id,
                    chat_id=chat_id,
                    timezone=timezone_validated,
                    created_at=datetime.now(dt_timezone.utc),
                    last_activity=datetime.now(dt_timezone.utc)
                )
                
                session.add(user)
                session.commit()
                session.refresh(user)
                
                # Create comprehensive default user settings
                self._create_default_user_settings(user_id)
                
                logger.info(f"Created user {user_id} with chat_id {chat_id}")
                return user
                
        except IntegrityError as e:
            logger.error(f"Integrity error creating user {user_id}: {e}")
            # Try to get existing user
            with self.get_session() as session:
                return session.query(User).filter(User.id == user_id).first()
        except SQLAlchemyError as e:
            logger.error(f"Database error creating user {user_id}: {e}")
            raise
    
    def _create_default_user_settings(self, user_id: int):
        """Create comprehensive default settings for new user"""
        try:
            with self.get_session() as session:
                # Check if settings already exist
                existing_settings = session.query(UserSettings).filter(UserSettings.user_id == user_id).first()
                if existing_settings:
                    return
                
                # Create default advanced settings
                advanced_settings = {
                    'onboarding_completed': True,
                    'first_summary_sent': False,
                    'preferred_insight_types': ['patterns', 'triggers', 'time_based'],
                    'custom_emotion_categories': [],
                    'export_preferences': {
                        'include_insights': True,
                        'date_format': 'YYYY-MM-DD'
                    }
                }
                
                settings = UserSettings(
                    user_id=user_id,
                    weekly_summary_enabled=True,
                    summary_time_hour=21,
                    ping_frequency='normal',
                    weekend_pings=True,
                    data_retention_days=365,
                    preferred_language='ru',
                    emoji_style='default',
                    advanced_settings=json.dumps(advanced_settings, ensure_ascii=False),
                    created_at=datetime.now(dt_timezone.utc),
                    updated_at=datetime.now(dt_timezone.utc)
                )
                
                session.add(settings)
                session.commit()
                
                logger.info(f"Created comprehensive default settings for user {user_id}")
                
        except SQLAlchemyError as e:
            logger.error(f"Error creating default settings for user {user_id}: {e}")
    
    def get_user(self, user_id: int) -> Optional[User]:
        """Get user by ID with error handling"""
        try:
            with self.get_session() as session:
                return session.query(User).filter(User.id == user_id).first()
        except SQLAlchemyError as e:
            logger.error(f"Database error getting user {user_id}: {e}")
            return None
    
    def get_user_by_chat_id(self, chat_id: int) -> Optional[User]:
        """Get user by chat ID with error handling"""
        try:
            with self.get_session() as session:
                return session.query(User).filter(User.chat_id == chat_id).first()
        except SQLAlchemyError as e:
            logger.error(f"Database error getting user by chat_id {chat_id}: {e}")
            return None
    
    def get_user_settings(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user settings as comprehensive dictionary"""
        try:
            with self.get_session() as session:
                settings = session.query(UserSettings).filter(UserSettings.user_id == user_id).first()
                if not settings:
                    # Create default settings if they don't exist
                    self._create_default_user_settings(user_id)
                    settings = session.query(UserSettings).filter(UserSettings.user_id == user_id).first()
                
                if settings:
                    result = {
                        # Core settings
                        'weekly_summary_enabled': settings.weekly_summary_enabled,
                        'summary_time_hour': settings.summary_time_hour,
                        'ping_frequency': settings.ping_frequency,
                        'weekend_pings': settings.weekend_pings,
                        'data_retention_days': settings.data_retention_days,
                        'preferred_language': settings.preferred_language,
                        'emoji_style': settings.emoji_style,
                        
                        # Metadata
                        'created_at': settings.created_at,
                        'updated_at': settings.updated_at
                    }
                    
                    # Add advanced settings from JSON
                    if settings.advanced_settings:
                        try:
                            advanced = json.loads(settings.advanced_settings)
                            result['advanced'] = advanced
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid advanced settings JSON for user {user_id}")
                            result['advanced'] = {}
                    else:
                        result['advanced'] = {}
                    
                    return result
                
                return None
                
        except SQLAlchemyError as e:
            logger.error(f"Database error getting settings for user {user_id}: {e}")
            return None
    
    def update_user_settings(self, user_id: int, **kwargs):
        """Update user settings with comprehensive options"""
        try:
            with self.get_session() as session:
                settings = session.query(UserSettings).filter(UserSettings.user_id == user_id).first()
                
                if not settings:
                    # Create default settings first
                    self._create_default_user_settings(user_id)
                    settings = session.query(UserSettings).filter(UserSettings.user_id == user_id).first()
                
                if settings:
                    # Update core settings
                    if 'weekly_summary_enabled' in kwargs:
                        settings.weekly_summary_enabled = bool(kwargs['weekly_summary_enabled'])
                    
                    if 'summary_time_hour' in kwargs:
                        hour = int(kwargs['summary_time_hour'])
                        if 0 <= hour <= 23:
                            settings.summary_time_hour = hour
                    
                    if 'ping_frequency' in kwargs:
                        frequency = kwargs['ping_frequency']
                        if frequency in ['normal', 'reduced', 'minimal']:
                            settings.ping_frequency = frequency
                    
                    if 'weekend_pings' in kwargs:
                        settings.weekend_pings = bool(kwargs['weekend_pings'])
                    
                    if 'data_retention_days' in kwargs:
                        days = int(kwargs['data_retention_days'])
                        if 30 <= days <= 3650:  # 1 month to 10 years
                            settings.data_retention_days = days
                    
                    if 'preferred_language' in kwargs:
                        lang = kwargs['preferred_language']
                        if lang in ['ru', 'en']:  # Support for future languages
                            settings.preferred_language = lang
                    
                    if 'emoji_style' in kwargs:
                        style = kwargs['emoji_style']
                        if style in ['default', 'minimal', 'colorful']:
                            settings.emoji_style = style
                    
                    # Update advanced settings
                    advanced_settings = {}
                    if settings.advanced_settings:
                        try:
                            advanced_settings = json.loads(settings.advanced_settings)
                        except json.JSONDecodeError:
                            advanced_settings = {}
                    
                    # Handle advanced settings updates
                    for key, value in kwargs.items():
                        if key.startswith('advanced_'):
                            setting_key = key.replace('advanced_', '')
                            advanced_settings[setting_key] = value
                        elif key not in ['weekly_summary_enabled', 'summary_time_hour', 'ping_frequency', 
                                       'weekend_pings', 'data_retention_days', 'preferred_language', 'emoji_style']:
                            # Store other custom settings in advanced
                            advanced_settings[key] = value
                    
                    settings.advanced_settings = json.dumps(advanced_settings, ensure_ascii=False)
                    settings.updated_at = datetime.now(dt_timezone.utc)
                    
                    session.commit()
                    
                    logger.info(f"Updated settings for user {user_id}")
                
        except SQLAlchemyError as e:
            logger.error(f"Database error updating settings for user {user_id}: {e}")
            raise
    
    def update_user_timezone(self, user_id: int, user_timezone: str):
        """Update user timezone with validation"""
        # Validate timezone
        timezone_validated = sanitize_user_input(user_timezone, "general")
        if not timezone_validated:
            raise ValueError("Invalid timezone")
        
        try:
            import zoneinfo
            zoneinfo.ZoneInfo(timezone_validated)  # Validate timezone
        except Exception:
            raise ValueError("Invalid timezone format")
        
        try:
            with self.get_session() as session:
                user = session.query(User).filter(User.id == user_id).first()
                if user:
                    user.timezone = timezone_validated
                    user.last_activity = datetime.now(dt_timezone.utc)
                    session.commit()
                    logger.info(f"Updated timezone for user {user_id} to {timezone_validated}")
                else:
                    logger.warning(f"User {user_id} not found for timezone update")
        except SQLAlchemyError as e:
            logger.error(f"Database error updating timezone for user {user_id}: {e}")
            raise
    
    def update_user_paused(self, user_id: int, paused: bool):
        """Update user paused status with validation"""
        if not isinstance(paused, bool):
            raise ValueError("Paused must be boolean")
        
        try:
            with self.get_session() as session:
                user = session.query(User).filter(User.id == user_id).first()
                if user:
                    user.paused = paused
                    user.last_activity = datetime.now(dt_timezone.utc)
                    session.commit()
                    logger.info(f"Updated paused status for user {user_id} to {paused}")
                else:
                    logger.warning(f"User {user_id} not found for paused update")
        except SQLAlchemyError as e:
            logger.error(f"Database error updating paused status for user {user_id}: {e}")
            raise
    
    def get_active_users(self) -> List[User]:
        """Get all active (non-paused) users with error handling"""
        try:
            with self.get_session() as session:
                return session.query(User).filter(User.paused == False).all()
        except SQLAlchemyError as e:
            logger.error(f"Database error getting active users: {e}")
            return []
    
    def get_users_for_weekly_summary(self) -> List[User]:
        """Get users who have weekly summaries enabled"""
        try:
            with self.get_session() as session:
                # Join users with settings to get only those with weekly summaries enabled
                users = (session.query(User)
                        .join(UserSettings, User.id == UserSettings.user_id)
                        .filter(User.paused == False)
                        .filter(UserSettings.weekly_summary_enabled == True)
                        .all())
                return users
        except SQLAlchemyError as e:
            logger.error(f"Database error getting users for weekly summary: {e}")
            return []
    
    def delete_user_data(self, user_id: int):
        """Delete all data for a user with transaction safety"""
        try:
            with self.get_session() as session:
                # Use transaction to ensure atomicity
                with session.begin():
                    # Delete entries
                    entries_deleted = session.query(Entry).filter(Entry.user_id == user_id).delete()
                    
                    # Delete schedules
                    schedules_deleted = session.query(Schedule).filter(Schedule.user_id == user_id).delete()
                    
                    # Delete summary deliveries
                    summaries_deleted = session.query(SummaryDelivery).filter(SummaryDelivery.user_id == user_id).delete()
                    
                    # Delete user settings
                    settings_deleted = session.query(UserSettings).filter(UserSettings.user_id == user_id).delete()
                    
                    # Delete user
                    user_deleted = session.query(User).filter(User.id == user_id).delete()
                    
                    logger.info(f"Deleted user {user_id}: {entries_deleted} entries, "
                              f"{schedules_deleted} schedules, {summaries_deleted} summaries, "
                              f"{settings_deleted} settings, {user_deleted} user record")
                              
        except SQLAlchemyError as e:
            logger.error(f"Database error deleting user data for {user_id}: {e}")
            raise
    
    def create_entry(self, user_id: int, emotions: str = None, cause: str = None, 
                    note: str = None, valence: int = None, arousal: int = None,
                    body: str = None, tags: str = None) -> Entry:
        """Create new emotion entry with comprehensive validation"""
        
        # Input validation
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("Invalid user_id")
        
        # Validate and sanitize text inputs
        emotions_validated = None
        if emotions:
            emotions_validated = sanitize_user_input(emotions, "general")
            if emotions_validated and len(emotions_validated) > 2000:
                emotions_validated = emotions_validated[:2000]
        
        cause_validated = None
        if cause:
            cause_validated = sanitize_user_input(cause, "cause")
            if cause_validated and len(cause_validated) > 2000:
                cause_validated = cause_validated[:2000]
        
        note_validated = None
        if note:
            note_validated = sanitize_user_input(note, "note")
            if note_validated and len(note_validated) > 2000:
                note_validated = note_validated[:2000]
        
        body_validated = None
        if body:
            body_validated = sanitize_user_input(body, "general")
            if body_validated and len(body_validated) > 1000:
                body_validated = body_validated[:1000]
        
        tags_validated = None
        if tags:
            tags_validated = sanitize_user_input(tags, "general")
            if tags_validated and len(tags_validated) > 500:
                tags_validated = tags_validated[:500]
        
        # Validate valence and arousal
        if valence is not None:
            if not isinstance(valence, int) or valence < -5 or valence > 5:
                valence = None
        
        if arousal is not None:
            if not isinstance(arousal, int) or arousal < -5 or arousal > 5:
                arousal = None
        
        try:
            with self.get_session() as session:
                # Get user timezone for local timestamp
                user = session.query(User).filter(User.id == user_id).first()
                if not user:
                    raise ValueError(f"User {user_id} not found")
                
                import zoneinfo
                tz = zoneinfo.ZoneInfo(user.timezone)
                local_time = datetime.now(tz).replace(tzinfo=None)  # Store as naive datetime
                
                entry = Entry(
                    user_id=user_id,
                    ts_local=local_time,
                    emotions=emotions_validated,
                    cause=cause_validated,
                    note=note_validated,
                    valence=valence,
                    arousal=arousal,
                    body=body_validated,
                    tags=tags_validated,
                    created_at=datetime.now(dt_timezone.utc)
                )
                
                session.add(entry)
                
                # Update user last activity
                user.last_activity = datetime.now(dt_timezone.utc)
                
                session.commit()
                session.refresh(entry)
                
                logger.info(f"Created entry for user {user_id}")
                return entry
                
        except SQLAlchemyError as e:
            logger.error(f"Database error creating entry for user {user_id}: {e}")
            raise
    
    # NEW: Summary delivery tracking methods
    def record_summary_delivery(self, user_id: int, period_days: int = 7, 
                               delivery_type: str = 'automatic', entries_count: int = 0, 
                               success: bool = True):
        """Record that a summary was delivered to user"""
        try:
            with self.get_session() as session:
                import zoneinfo
                
                # Get user timezone for local date
                user = session.query(User).filter(User.id == user_id).first()
                if user:
                    try:
                        tz = zoneinfo.ZoneInfo(user.timezone)
                        local_date = datetime.now(tz).date()
                    except Exception:
                        local_date = datetime.now().date()
                else:
                    local_date = datetime.now().date()
                
                delivery = SummaryDelivery(
                    user_id=user_id,
                    delivery_date=local_date,
                    summary_period_days=period_days,
                    delivery_type=delivery_type,
                    entries_count=entries_count,
                    success=success,
                    created_at=datetime.now(dt_timezone.utc)
                )
                
                session.add(delivery)
                session.commit()
                
                logger.info(f"Recorded summary delivery for user {user_id}: {period_days} days, {entries_count} entries")
                
        except SQLAlchemyError as e:
            logger.error(f"Database error recording summary delivery for user {user_id}: {e}")
    
    def get_last_summary_delivery(self, user_id: int, delivery_type: str = 'automatic') -> Optional[SummaryDelivery]:
        """Get the last summary delivery for user"""
        try:
            with self.get_session() as session:
                return (session.query(SummaryDelivery)
                       .filter(SummaryDelivery.user_id == user_id)
                       .filter(SummaryDelivery.delivery_type == delivery_type)
                       .filter(SummaryDelivery.success == True)
                       .order_by(SummaryDelivery.created_at.desc())
                       .first())
        except SQLAlchemyError as e:
            logger.error(f"Database error getting last summary delivery for user {user_id}: {e}")
            return None
    
    def get_user_entries(self, user_id: int, days: int = 7) -> List[Entry]:
        """Get user entries from last N days with validation"""
        if not isinstance(user_id, int) or user_id <= 0:
            return []
        
        if not isinstance(days, int) or days <= 0:
            days = 7
        
        # Limit days to reasonable range
        days = min(days, 365)
        
        try:
            with self.get_session() as session:
                from datetime import timedelta
                
                # Get user timezone
                user = session.query(User).filter(User.id == user_id).first()
                if not user:
                    return []
                
                import zoneinfo
                tz = zoneinfo.ZoneInfo(user.timezone)
                cutoff_date = (datetime.now(tz) - timedelta(days=days)).replace(tzinfo=None)
                
                return (session.query(Entry)
                       .filter(Entry.user_id == user_id)
                       .filter(Entry.ts_local >= cutoff_date)
                       .order_by(Entry.ts_local.desc())
                       .limit(10000)  # Safety limit
                       .all())
                       
        except SQLAlchemyError as e:
            logger.error(f"Database error getting entries for user {user_id}: {e}")
            return []
    
    def get_user_schedule(self, user_id: int, date_local: date) -> Optional[Schedule]:
        """Get user schedule for specific date with validation"""
        if not isinstance(user_id, int) or user_id <= 0:
            return None
        
        if not isinstance(date_local, date):
            return None
        
        try:
            with self.get_session() as session:
                return (session.query(Schedule)
                       .filter(Schedule.user_id == user_id)
                       .filter(Schedule.date_local == date_local)
                       .first())
        except SQLAlchemyError as e:
            logger.error(f"Database error getting schedule for user {user_id}: {e}")
            return None
    
    def save_user_schedule(self, user_id: int, date_local: date, times_json: str):
        """Save user schedule for specific date with validation"""
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("Invalid user_id")
        
        if not isinstance(date_local, date):
            raise ValueError("Invalid date")
        
        # Validate JSON
        times_validated = sanitize_user_input(times_json, "general")
        if not times_validated:
            raise ValueError("Invalid times JSON")
        
        try:
            # Test JSON parsing
            json.loads(times_validated)
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON format")
        
        try:
            with self.get_session() as session:
                with session.begin():
                    # Delete existing schedule for this date
                    session.query(Schedule).filter(
                        Schedule.user_id == user_id,
                        Schedule.date_local == date_local
                    ).delete()
                    
                    # Create new schedule
                    schedule = Schedule(
                        user_id=user_id,
                        date_local=date_local,
                        times_local=times_validated,
                        created_at=datetime.now(dt_timezone.utc)
                    )
                    
                    session.add(schedule)
                    
        except SQLAlchemyError as e:
            logger.error(f"Database error saving schedule for user {user_id}: {e}")
            raise
    
    def get_global_stats(self) -> Dict[str, int]:
        """Get global bot statistics (no personal data) with error handling"""
        try:
            with self.get_session() as session:
                from datetime import timedelta
                
                # Total users
                total_users = session.query(User).count()
                
                # Total entries
                total_entries = session.query(Entry).count()
                
                # Active users (last 7 days)
                week_ago = datetime.now(dt_timezone.utc) - timedelta(days=7)
                active_weekly = (session.query(User)
                                .filter(User.last_activity >= week_ago)
                                .count())
                
                # Users with weekly summary enabled
                weekly_summary_users = (session.query(UserSettings)
                                       .filter(UserSettings.weekly_summary_enabled == True)
                                       .count())
                
                # Summary deliveries this week
                week_start = datetime.now(dt_timezone.utc) - timedelta(days=7)
                summaries_this_week = (session.query(SummaryDelivery)
                                      .filter(SummaryDelivery.created_at >= week_start)
                                      .filter(SummaryDelivery.success == True)
                                      .count())
                
                return {
                    'total_users': total_users,
                    'total_entries': total_entries,
                    'active_weekly': active_weekly,
                    'weekly_summary_users': weekly_summary_users,
                    'summaries_this_week': summaries_this_week
                }
                
        except SQLAlchemyError as e:
            logger.error(f"Database error getting global stats: {e}")
            return {
                'total_users': 0,
                'total_entries': 0,
                'active_weekly': 0,
                'weekly_summary_users': 0,
                'summaries_this_week': 0
            }
    
    def get_emotion_frequencies(self, user_id: int, days: int = 7) -> Dict[str, int]:
        """Get emotion word frequencies for user with validation"""
        entries = self.get_user_entries(user_id, days)
        
        emotion_counts = {}
        
        for entry in entries:
            if entry.emotions:
                try:
                    emotions_list = json.loads(entry.emotions)
                    for emotion in emotions_list:
                        if isinstance(emotion, str):
                            emotion_clean = sanitize_user_input(emotion, "emotion")
                            if emotion_clean:
                                emotion_counts[emotion_clean] = emotion_counts.get(emotion_clean, 0) + 1
                except (json.JSONDecodeError, TypeError):
                    # Handle plain text emotions
                    emotion_clean = sanitize_user_input(entry.emotions, "emotion")
                    if emotion_clean:
                        emotion_counts[emotion_clean] = emotion_counts.get(emotion_clean, 0) + 1
        
        return emotion_counts
    
    def get_cause_frequencies(self, user_id: int, days: int = 7) -> Dict[str, int]:
        """Get cause/trigger frequencies for user with validation"""
        entries = self.get_user_entries(user_id, days)
        
        cause_counts = {}
        
        for entry in entries:
            if entry.cause:
                cause_clean = sanitize_user_input(entry.cause, "cause")
                if cause_clean:
                    # Simple keyword extraction (in production, use NLP)
                    words = cause_clean.lower().split()
                    for word in words:
                        if len(word) > 3:  # Skip short words
                            word_clean = sanitize_user_input(word, "general")
                            if word_clean:
                                cause_counts[word_clean] = cause_counts.get(word_clean, 0) + 1
        
        return cause_counts
    
    def get_time_distribution(self, user_id: int, days: int = 7) -> Dict[int, int]:
        """Get distribution of entries by hour of day with validation"""
        entries = self.get_user_entries(user_id, days)
        
        hour_counts = {}
        
        for entry in entries:
            hour = entry.ts_local.hour
            if 0 <= hour <= 23:  # Validate hour
                hour_counts[hour] = hour_counts.get(hour, 0) + 1
        
        return hour_counts
    
    def cleanup_old_schedules(self, days_old: int = 7):
        """Clean up old schedule records with safety limits"""
        if not isinstance(days_old, int) or days_old < 1:
            days_old = 7
        
        # Safety limit: don't delete schedules newer than 1 day
        days_old = max(days_old, 1)
        
        try:
            with self.get_session() as session:
                from datetime import timedelta
                
                cutoff_date = datetime.now().date() - timedelta(days=days_old)
                
                # Use limit to prevent accidental mass deletion
                deleted = (session.query(Schedule)
                          .filter(Schedule.date_local < cutoff_date)
                          .limit(1000)  # Safety limit
                          .delete(synchronize_session=False))
                
                session.commit()
                
                if deleted > 0:
                    logger.info(f"Cleaned up {deleted} old schedule records")
                    
        except SQLAlchemyError as e:
            logger.error(f"Database error during cleanup: {e}")
    
    def health_check(self) -> bool:
        """Simple database health check"""
        try:
            with self.get_session() as session:
                session.execute("SELECT 1").fetchone()
                return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False


def test_database():
    """Enhanced database test with user settings and summary tracking"""
    import tempfile
    import os
    
    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        test_db_path = f.name
    
    try:
        db = Database(f'sqlite:///{test_db_path}')
        
        # Test health check
        assert db.health_check(), "Health check failed"
        
        # Test user creation (should create settings automatically)
        user = db.create_user(12345, 67890, 'Europe/Moscow')
        assert user.id == 12345
        assert user.chat_id == 67890
        
        # Test comprehensive user settings
        settings = db.get_user_settings(12345)
        assert settings is not None
        assert settings['weekly_summary_enabled'] == True
        assert settings['summary_time_hour'] == 21
        assert settings['ping_frequency'] == 'normal'
        assert settings['weekend_pings'] == True
        assert 'advanced' in settings
        
        # Test updating comprehensive settings
        db.update_user_settings(12345, 
                               weekly_summary_enabled=False, 
                               summary_time_hour=20,
                               ping_frequency='reduced',
                               weekend_pings=False,
                               advanced_custom_feature=True)
        
        updated_settings = db.get_user_settings(12345)
        assert updated_settings['weekly_summary_enabled'] == False
        assert updated_settings['summary_time_hour'] == 20
        assert updated_settings['ping_frequency'] == 'reduced'
        assert updated_settings['weekend_pings'] == False
        assert updated_settings['advanced']['custom_feature'] == True
        
        # Test entry creation
        entry = db.create_entry(
            user_id=12345,
            emotions='["радость", "удовлетворение"]',
            cause='закончил проект',
            note='отличное настроение'
        )
        assert entry.user_id == 12345
        
        # Test summary delivery recording
        db.record_summary_delivery(12345, period_days=7, entries_count=5)
        last_delivery = db.get_last_summary_delivery(12345)
        assert last_delivery is not None
        assert last_delivery.entries_count == 5
        
        # Test entry retrieval
        entries = db.get_user_entries(12345, 7)
        assert len(entries) >= 1
        
        # Test enhanced statistics
        stats = db.get_global_stats()
        assert stats['total_users'] >= 1
        assert stats['total_entries'] >= 1
        assert 'weekly_summary_users' in stats
        assert 'summaries_this_week' in stats
        
        # Test users for weekly summary
        weekly_users = db.get_users_for_weekly_summary()
        assert len(weekly_users) == 0  # User has weekly summary disabled
        
        # Re-enable and test again
        db.update_user_settings(12345, weekly_summary_enabled=True)
        weekly_users = db.get_users_for_weekly_summary()
        assert len(weekly_users) >= 1
        
        print("Enhanced database tests passed!")
        
    finally:
        # Cleanup
        os.unlink(test_db_path)


if __name__ == "__main__":
    test_database()
