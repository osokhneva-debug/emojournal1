#!/usr/bin/env python3
"""
Random Scheduler for EmoJournal Bot
Generates 4 random daily slots with ≥2h spacing
"""

import logging
import random
import asyncio
from datetime import datetime, timedelta, time
from typing import List, Optional
import json
from .db import Database

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor

logger = logging.getLogger(__name__)

class RandomScheduler:
    """Handles random emotion ping scheduling with persistence"""
    
    # Configuration constants
    WINDOW_START_HOUR = 9   # 09:00
    WINDOW_END_HOUR = 23    # 23:00  
    DAILY_PINGS = 4
    MIN_INTERVAL_MINUTES = 120  # 2 hours minimum between pings
    
    def __init__(self, db):
        self.db = db
        self.scheduler = None
        
    async def start(self):
        """Initialize and start the scheduler"""
        # Configure job store to persist across restarts
        jobstores = {
            'default': SQLAlchemyJobStore(url=f"sqlite:///{self.db.db_path}")
        }
        
        executors = {
            'default': AsyncIOExecutor()
        }
        
        job_defaults = {
            'coalesce': False,
            'max_instances': 3
        }
        
        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone='Europe/Moscow'  # Default timezone
        )
        
        self.scheduler.start()
        
        # Schedule daily schedule generation for all active users
        self.scheduler.add_job(
            self._daily_schedule_all_users,
            'cron',
            hour=8,
            minute=55,
            id='daily_schedule_generator',
            replace_existing=True
        )
        
        logger.info("Random scheduler started")
    
    def generate_random_times(self, target_date: datetime = None) -> List[time]:
        """
        Generate 4 random times between 09:00-23:00 with ≥2h spacing
        
        Algorithm:
        1. Convert time window to minutes since midnight
        2. Iteratively sample random minutes, ensuring ≥120min spacing
        3. Return sorted list of time objects
        """
        if target_date is None:
            target_date = datetime.now()
        
        # Convert window to minutes since midnight
        window_start_min = self.WINDOW_START_HOUR * 60  # 540 minutes (09:00)
        window_end_min = self.WINDOW_END_HOUR * 60      # 1380 minutes (23:00)
        
        selected_minutes = []
        max_attempts = 500
        
        for _ in range(self.DAILY_PINGS):
            attempts = 0
            
            while attempts < max_attempts:
                # Sample random minute in window
                candidate_min = random.randint(window_start_min, window_end_min - 1)
                
                # Check minimum distance constraint
                valid = True
                for existing_min in selected_minutes:
                    if abs(candidate_min - existing_min) < self.MIN_INTERVAL_MINUTES:
                        valid = False
                        break
                
                if valid:
                    selected_minutes.append(candidate_min)
                    break
                    
                attempts += 1
            
            if attempts >= max_attempts:
                logger.warning(f"Failed to generate slot {len(selected_minutes) + 1} after {max_attempts} attempts")
                # Fallback: use remaining window space
                if selected_minutes:
                    last_time = max(selected_minutes)
                    fallback_time = last_time + self.MIN_INTERVAL_MINUTES
                    if fallback_time < window_end_min:
                        selected_minutes.append(fallback_time)
        
        # Convert minutes back to time objects and sort
        selected_minutes.sort()
        times = []
        
        for minutes in selected_minutes:
            hour = minutes // 60
            minute = minutes % 60
            times.append(time(hour=hour, minute=minute))
        
        logger.debug(f"Generated random times: {[t.strftime('%H:%M') for t in times]}")
        return times
    
    def validate_time_spacing(self, times: List[time]) -> bool:
        """Validate that all times have ≥2h spacing"""
        if len(times) < 2:
            return True
            
        # Convert times to minutes for easy comparison
        minutes = [t.hour * 60 + t.minute for t in times]
        minutes.sort()
        
        # Check all pairs
        for i in range(len(minutes) - 1):
            if minutes[i + 1] - minutes[i] < self.MIN_INTERVAL_MINUTES:
                return False
                
        return True
    
    async def start_user_schedule(self, user_id: int):
        """Start daily scheduling for a specific user"""
        if not self.scheduler:
            logger.warning("Scheduler not initialized")
            return
            
        user = self.db.get_user(user_id)
        if not user or user.paused:
            return
        
        # Remove existing jobs for this user
        await self.stop_user_schedule(user_id)
        
        # Generate today's schedule if not exists or incomplete
        await self._ensure_todays_schedule(user_id, user.timezone)
        
        # Schedule daily regeneration
        self.scheduler.add_job(
            self._generate_user_daily_schedule,
            'cron',
            hour=8,
            minute=55,
            args=[user_id],
            id=f'daily_schedule_{user_id}',
            timezone=user.timezone,
            replace_existing=True
        )
        
        logger.info(f"Started scheduling for user {user_id}")
    
    async def stop_user_schedule(self, user_id: int):
        """Stop scheduling for a user"""
        if not self.scheduler:
            return
            
        # Remove daily schedule job
        try:
            self.scheduler.remove_job(f'daily_schedule_{user_id}')
        except:
            pass
        
        # Remove today's ping jobs
        today_str = datetime.now().strftime('%Y%m%d')
        for i in range(self.DAILY_PINGS):
            try:
                self.scheduler.remove_job(f'ping_{user_id}_{today_str}_{i}')
            except:
                pass
        
        logger.info(f"Stopped scheduling for user {user_id}")
    
    async def _ensure_todays_schedule(self, user_id: int, user_timezone: str = 'Europe/Moscow'):
        """Ensure today's schedule exists and create missing ping jobs"""
        import zoneinfo
        
        tz = zoneinfo.ZoneInfo(user_timezone)
        now = datetime.now(tz)
        today = now.date()
        
        # Check if schedule exists for today
        schedule = self.db.get_user_schedule(user_id, today)
        
        if not schedule:
            # Generate new schedule for today
            times = self.generate_random_times(now)
            times_json = json.dumps([t.strftime('%H:%M') for t in times])
            self.db.save_user_schedule(user_id, today, times_json)
            schedule_times = times
        else:
            # Load existing schedule
            times_data = json.loads(schedule.times_local)
            schedule_times = [
                datetime.strptime(t, '%H:%M').time() 
                for t in times_data
            ]
        
        # Create ping jobs for remaining slots (future times only)
        today_str = today.strftime('%Y%m%d')
        
        for i, ping_time in enumerate(schedule_times):
            ping_datetime = datetime.combine(today, ping_time, tzinfo=tz)
            
            # Only schedule if time is in the future
            if ping_datetime > now:
                job_id = f'ping_{user_id}_{today_str}_{i}'
                
                # Remove existing job if any
                try:
                    self.scheduler.remove_job(job_id)
                except:
