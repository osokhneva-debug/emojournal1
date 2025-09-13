#!/usr/bin/env python3
"""
Database models and access layer for EmoJournal Bot
SQLite with SQLAlchemy for persistence
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

# Create indexes
Index('idx_entries_user_date', Entry.user_id, Entry.ts_local)
Index('idx_schedules_user_date', Schedule.user_id, Schedule.date_local)

class Database:
    """Database access layer"""
    
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
    
    def create_user(self, user_id: int, chat_id: int, timezone: str = 'Europe/Moscow') -> User:
        """Create new user"""
        with self.get_session() as session:
            user = User(
                id=user_id,
                chat_id=chat_id,
                timezone=timezone,
                created_at=datetime.now(datetime.timezone.utc),
                last_activity=datetime.now(datetime.timezone.utc)
            )
            
            session.add(user)
            session.commit()
            session.refresh(user)
            
            logger.info(f"Created user {user_id} with chat_id {chat_id}")
            return user
    
    def get_user(self, user_id: int) -> Optional[User]:
        """Get user by ID"""
        with self.get_session() as session:
            return session.query(User).filter(User.id == user_id).first()
    
    def get_user_by_chat_id(self, chat_id: int) -> Optional[User]:
        """Get user by chat ID"""
        with self.get_session() as session:
            return session.query(User).filter(User.chat_id == chat_id).first()
    
    def update_user_timezone(self, user_id: int, timezone: str):
        """Update user timezone"""
        with self.get_session() as session:
            user = session.query(User).filter(User.id == user_id).first()
            if user:
                user.timezone = timezone
                user.last_activity = datetime.now(datetime.timezone.utc)
                session.commit()
                logger.info(f"Updated timezone for user {user_id} to {timezone}")
    
    def update_user_paused(self, user_id: int, paused: bool):
        """Update user paused status"""
        with self.get_session() as session:
            user = session.query(User).filter(User.id == user_id).first()
            if user:
                user.paused = paused
                user.last_activity = datetime.now(datetime.timezone.utc)
                session.commit()
                logger.info(f"Updated paused status for user {user_id} to {paused}")
    
    def get_active_users(self) -> List[User]:
        """Get all active (non-paused) users"""
        with self.get_session() as session:
            return session.query(User).filter(User.paused == False).all()
    
    def delete_user_data(self, user_id: int):
        """Delete all data for a user"""
        with self.get_session() as session:
            # Delete entries
            session.query(Entry).filter(Entry.user_id == user_id).delete()
            
            # Delete schedules
            session.query(Schedule).filter(Schedule.user_id == user_id).delete()
            
            # Delete user
            session.query(User).filter(User.id == user_id).delete()
            
            session.commit()
            logger.info(f"Deleted all data for user {user_id}")
    
    def create_entry(self, user_id: int, emotions: str = None, cause: str = None, 
                    note: str = None, valence: int = None, arousal: int = None,
                    body: str = None, tags: str = None) -> Entry:
        """Create new emotion entry"""
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
                emotions=emotions,
                cause=cause,
                note=note,
                valence=valence,
                arousal=arousal,
                body=body,
                tags=tags,
                created_at=datetime.now(datetime.timezone.utc)
            )
            
            session.add(entry)
            
            # Update user last activity
            user.last_activity = datetime.now(datetime.timezone.utc)
            
            session.commit()
            session.refresh(entry)
            
            logger.info(f"Created entry for user {user_id}")
            return entry
    
    def get_user_entries(self, user_id: int, days: int = 7) -> List[Entry]:
        """Get user entries from last N days"""
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
                   .all())
    
    def get_user_schedule(self, user_id: int, date_local: date) -> Optional[Schedule]:
        """Get user schedule for specific date"""
        with self.get_session() as session:
            return (session.query(Schedule)
                   .filter(Schedule.user_id == user_id)
                   .filter(Schedule.date_local == date_local)
                   .first())
    
    def save_user_schedule(self, user_id: int, date_local: date, times_json: str):
        """Save user schedule for specific date"""
        with self.get_session() as session:
            # Delete existing schedule for this date
            session.query(Schedule).filter(
                Schedule.user_id == user_id,
                Schedule.date_local == date_local
            ).delete()
            
            # Create new schedule
            schedule = Schedule(
                user_id=user_id,
                date_local=date_local,
                times_local=times_json,
                created_at=datetime.now(datetime.timezone.utc)
            )
            
            session.add(schedule)
            session.commit()
    
    def get_global_stats(self) -> Dict[str, int]:
        """Get global bot statistics (no personal data)"""
        with self.get_session() as session:
            from datetime import timedelta
            
            # Total users
            total_users = session.query(User).count()
            
            # Total entries
            total_entries = session.query(Entry).count()
            
            # Active users (last 7 days)
            week_ago = datetime.now(datetime.timezone.utc) - timedelta(days=7)
            active_weekly = (session.query(User)
                            .filter(User.last_activity >= week_ago)
                            .count())
            
            return {
                'total_users': total_users,
                'total_entries': total_entries,
                'active_weekly': active_weekly
            }
    
    def get_emotion_frequencies(self, user_id: int, days: int = 7) -> Dict[str, int]:
        """Get emotion word frequencies for user"""
        entries = self.get_user_entries(user_id, days)
        
        emotion_counts = {}
        
        for entry in entries:
            if entry.emotions:
                try:
                    emotions_list = json.loads(entry.emotions)
                    for emotion in emotions_list:
                        emotion = emotion.lower().strip()
                        if emotion:
                            emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1
                except json.JSONDecodeError:
                    # Handle plain text emotions
                    emotion = entry.emotions.lower().strip()
                    if emotion:
                        emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1
        
        return emotion_counts
    
    def get_cause_frequencies(self, user_id: int, days: int = 7) -> Dict[str, int]:
        """Get cause/trigger frequencies for user"""
        entries = self.get_user_entries(user_id, days)
        
        cause_counts = {}
        
        for entry in entries:
            if entry.cause:
                cause = entry.cause.lower().strip()
                if cause:
                    # Simple keyword extraction (in production, use NLP)
                    words = cause.split()
                    for word in words:
                        if len(word) > 3:  # Skip short words
                            cause_counts[word] = cause_counts.get(word, 0) + 1
        
        return cause_counts
    
    def get_time_distribution(self, user_id: int, days: int = 7) -> Dict[int, int]:
        """Get distribution of entries by hour of day"""
        entries = self.get_user_entries(user_id, days)
        
        hour_counts = {}
        
        for entry in entries:
            hour = entry.ts_local.hour
            hour_counts[hour] = hour_counts.get(hour, 0) + 1
        
        return hour_counts
    
    def cleanup_old_schedules(self, days_old: int = 7):
        """Clean up old schedule records"""
        with self.get_session() as session:
            from datetime import timedelta
            
            cutoff_date = datetime.now().date() - timedelta(days=days_old)
            
            deleted = (session.query(Schedule)
                      .filter(Schedule.date_local < cutoff_date)
                      .delete())
            
            session.commit()
            
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old schedule records")


def test_database():
    """Simple database test"""
    import tempfile
    import os
    
    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        test_db_path = f.name
    
    try:
        db = Database(f'sqlite:///{test_db_path}')
        
        # Test user creation
        user = db.create_user(12345, 67890, 'Europe/Moscow')
        assert user.id == 12345
        assert user.chat_id == 67890
        
        # Test user retrieval
        retrieved_user = db.get_user(12345)
        assert retrieved_user is not None
        assert retrieved_user.timezone == 'Europe/Moscow'
        
        # Test entry creation
        entry = db.create_entry(
            user_id=12345,
            emotions='["радость", "удовлетворение"]',
            cause='закончил проект',
            note='отличное настроение'
        )
        assert entry.user_id == 12345
        
        # Test entry retrieval
        entries = db.get_user_entries(12345, 7)
        assert len(entries) == 1
        assert entries[0].note == 'отличное настроение'
        
        # Test statistics
        stats = db.get_global_stats()
        assert stats['total_users'] == 1
        assert stats['total_entries'] == 1
        
        print("Database tests passed!")
        
    finally:
        # Cleanup
        os.unlink(test_db_path)


if __name__ == "__main__":
    test_database()
