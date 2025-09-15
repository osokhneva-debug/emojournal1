#!/usr/bin/env python3
"""
Fixed Scheduler for EmoJournal Bot
Generates 4 fixed daily slots at 9, 13, 17, 21 hours
"""

import logging
import asyncio
from datetime import datetime, timedelta, time
from typing import List, Optional
import json

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.executors.asyncio import AsyncIOExecutor

logger = logging.getLogger(__name__)

class FixedScheduler:
    """Handles fixed emotion ping scheduling"""
    
    # Configuration constants
    FIXED_HOURS = [9, 13, 17, 21]  # 4 раза в день: 9:00, 13:00, 17:00, 21:00
    
    def __init__(self, db):
        self.db = db
        self.scheduler = None
        
    async def start(self):
        """Initialize and start the scheduler"""
        # Simplified scheduler without persistent job store
        executors = {
            'default': AsyncIOExecutor()
        }
        
        job_defaults = {
            'coalesce': False,
            'max_instances': 3
        }
        
        self.scheduler = AsyncIOScheduler(
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
        
        logger.info("Fixed scheduler started")
    
    def generate_fixed_times(self) -> List[time]:
        """
        Generate 4 fixed times: 09:00, 13:00, 17:00, 21:00
        """
        times = []
        for hour in self.FIXED_HOURS:
            times.append(time(hour=hour, minute=0))
        
        logger.debug(f"Generated fixed times: {[t.strftime('%H:%M') for t in times]}")
        return times
    
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
        for i, hour in enumerate(self.FIXED_HOURS):
            try:
                self.scheduler.remove_job(f'ping_{user_id}_{today_str}_{hour}')
            except:
                pass
        
        logger.info(f"Stopped scheduling for user {user_id}")
    
    async def _ensure_todays_schedule(self, user_id: int, user_timezone: str = 'Europe/Moscow'):
        """Ensure today's schedule exists and create missing ping jobs"""
        import zoneinfo
        
        tz = zoneinfo.ZoneInfo(user_timezone)
        now = datetime.now(tz)
        today = now.date()
        
        # Generate fixed times
        times = self.generate_fixed_times()
        times_json = json.dumps([t.strftime('%H:%M') for t in times])
        
        # Save schedule to database (always overwrite for consistency)
        self.db.save_user_schedule(user_id, today, times_json)
        
        # Create ping jobs for remaining slots (future times only)
        today_str = today.strftime('%Y%m%d')
        
        for i, ping_time in enumerate(times):
            ping_datetime = datetime.combine(today, ping_time, tzinfo=tz)
            
            # Only schedule if time is in the future
            if ping_datetime > now:
                job_id = f'ping_{user_id}_{today_str}_{ping_time.hour}'
                
                # Remove existing job if any
                try:
                    self.scheduler.remove_job(job_id)
                except:
                    pass
                
                # Schedule ping
                self.scheduler.add_job(
                    self._send_simple_ping,
                    'date',
                    run_date=ping_datetime,
                    args=[user_id],
                    id=job_id,
                    replace_existing=True
                )
                
                logger.debug(f"Scheduled ping for user {user_id} at {ping_datetime}")
    
    async def _generate_user_daily_schedule(self, user_id: int):
        """Generate and schedule pings for a specific user (called daily at 08:55)"""
        user = self.db.get_user(user_id)
        if not user or user.paused:
            return
            
        import zoneinfo
        tz = zoneinfo.ZoneInfo(user.timezone)
        tomorrow = (datetime.now(tz) + timedelta(days=1)).date()
        
        # Generate fixed times for tomorrow
        times = self.generate_fixed_times()
        times_json = json.dumps([t.strftime('%H:%M') for t in times])
        
        # Save schedule to database
        self.db.save_user_schedule(user_id, tomorrow, times_json)
        
        # Schedule ping jobs for tomorrow
        tomorrow_str = tomorrow.strftime('%Y%m%d')
        
        for i, ping_time in enumerate(times):
            ping_datetime = datetime.combine(tomorrow, ping_time, tzinfo=tz)
            job_id = f'ping_{user_id}_{tomorrow_str}_{ping_time.hour}'
            
            self.scheduler.add_job(
                self._send_simple_ping,
                'date',
                run_date=ping_datetime,
                args=[user_id],
                id=job_id,
                replace_existing=True
            )
        
        logger.info(f"Generated schedule for user {user_id} on {tomorrow}: {[t.strftime('%H:%M') for t in times]}")
    
    async def _daily_schedule_all_users(self):
        """Generate schedules for all active users (runs daily at 08:55)"""
        active_users = self.db.get_active_users()
        
        for user in active_users:
            if not user.paused:
                try:
                    await self._generate_user_daily_schedule(user.id)
                except Exception as e:
                    logger.error(f"Failed to generate schedule for user {user.id}: {e}")
        
        logger.info(f"Generated daily schedules for {len(active_users)} users")
    
    async def _send_simple_ping(self, user_id: int):
        """Simplified ping function without complex dependencies"""
        try:
            import os
            bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
            
            from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
            bot = Bot(token=bot_token)
            
            user = self.db.get_user(user_id)
            if not user or user.paused:
                return
            
            keyboard = [
                [InlineKeyboardButton("Ответить", callback_data=f"respond_{user_id}")],
                [InlineKeyboardButton("Отложить на 15 мин", callback_data=f"snooze_{user_id}")],
                [InlineKeyboardButton("Пропустить сегодня", callback_data=f"skip_{user_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Simple hardcoded text instead of importing
            ping_text = """🌟 Как ты сейчас?

Если хочется — выбери 1-2 слова или просто опиши своими словами.

<i>Сам факт, что ты это заметишь и назовёшь, — уже шаг к ясности.</i>"""
            
            await bot.send_message(
                chat_id=user.chat_id,
                text=ping_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            
            logger.info(f"Sent emotion ping to user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to send ping to user {user_id}: {e}")
    
    async def schedule_snooze(self, user_id: int, minutes: int = 15):
        """Schedule a snoozed ping"""
        if not self.scheduler:
            return
            
        snooze_time = datetime.now() + timedelta(minutes=minutes)
        job_id = f'snooze_{user_id}_{int(snooze_time.timestamp())}'
        
        self.scheduler.add_job(
            self._send_simple_ping,
            'date',
            run_date=snooze_time,
            args=[user_id],
            id=job_id,
            replace_existing=True
        )
        
        logger.info(f"Scheduled snooze ping for user {user_id} in {minutes} minutes")
    
    async def skip_today(self, user_id: int):
        """Skip remaining pings for today"""
        if not self.scheduler:
            return
            
        import zoneinfo
        user = self.db.get_user(user_id)
        if not user:
            return
            
        tz = zoneinfo.ZoneInfo(user.timezone)
        today_str = datetime.now(tz).strftime('%Y%m%d')
        
        # Remove all remaining ping jobs for today
        for hour in self.FIXED_HOURS:
            job_id = f'ping_{user_id}_{today_str}_{hour}'
            try:
                self.scheduler.remove_job(job_id)
            except:
                pass
        
        logger.info(f"Skipped remaining pings for user {user_id} today")
    
    async def stop(self):
        """Stop the scheduler"""
        if self.scheduler:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")


def test_fixed_time_generation():
    """Unit test for fixed time generation"""
    scheduler = FixedScheduler(None)
    
    times = scheduler.generate_fixed_times()
    
    # Test conditions
    assert len(times) == 4, f"Expected 4 times, got {len(times)}"
    
    expected_hours = [9, 13, 17, 21]
    actual_hours = [t.hour for t in times]
    
    assert actual_hours == expected_hours, f"Expected hours {expected_hours}, got {actual_hours}"
    
    # All times should be at minute 0
    for t in times:
        assert t.minute == 0, f"Expected minute 0, got {t.minute} for {t}"
    
    print(f"Fixed time generation test passed: {[t.strftime('%H:%M') for t in times]}")
    return True


if __name__ == "__main__":
    # Run unit test
    test_fixed_time_generation()
    print("All tests passed!")#!/usr/bin/env python3
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

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.executors.asyncio import AsyncIOExecutor

logger = logging.getLogger(__name__)

class RandomScheduler:
    """Handles random emotion ping scheduling"""
    
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
        # Simplified scheduler without persistent job store
        executors = {
            'default': AsyncIOExecutor()
        }
        
        job_defaults = {
            'coalesce': False,
            'max_instances': 3
        }
        
        self.scheduler = AsyncIOScheduler(
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
                    pass
                
                # Schedule ping - simplified version without database objects
                self.scheduler.add_job(
                    self._send_simple_ping,
                    'date',
                    run_date=ping_datetime,
                    args=[user_id],
                    id=job_id,
                    replace_existing=True
                )
                
                logger.debug(f"Scheduled ping for user {user_id} at {ping_datetime}")
    
    async def _generate_user_daily_schedule(self, user_id: int):
        """Generate and schedule pings for a specific user (called daily at 08:55)"""
        user = self.db.get_user(user_id)
        if not user or user.paused:
            return
            
        import zoneinfo
        tz = zoneinfo.ZoneInfo(user.timezone)
        tomorrow = (datetime.now(tz) + timedelta(days=1)).date()
        
        # Generate random times for tomorrow
        times = self.generate_random_times()
        times_json = json.dumps([t.strftime('%H:%M') for t in times])
        
        # Save schedule to database
        self.db.save_user_schedule(user_id, tomorrow, times_json)
        
        # Schedule ping jobs for tomorrow
        tomorrow_str = tomorrow.strftime('%Y%m%d')
        
        for i, ping_time in enumerate(times):
            ping_datetime = datetime.combine(tomorrow, ping_time, tzinfo=tz)
            job_id = f'ping_{user_id}_{tomorrow_str}_{i}'
            
            self.scheduler.add_job(
                self._send_simple_ping,
                'date',
                run_date=ping_datetime,
                args=[user_id],
                id=job_id,
                replace_existing=True
            )
        
        logger.info(f"Generated schedule for user {user_id} on {tomorrow}: {[t.strftime('%H:%M') for t in times]}")
    
    async def _daily_schedule_all_users(self):
        """Generate schedules for all active users (runs daily at 08:55)"""
        active_users = self.db.get_active_users()
        
        for user in active_users:
            if not user.paused:
                try:
                    await self._generate_user_daily_schedule(user.id)
                except Exception as e:
                    logger.error(f"Failed to generate schedule for user {user.id}: {e}")
        
        logger.info(f"Generated daily schedules for {len(active_users)} users")
    
    async def _send_simple_ping(self, user_id: int):
        """Simplified ping function without complex dependencies"""
        try:
            import os
            bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
            
            from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
            bot = Bot(token=bot_token)
            
            user = self.db.get_user(user_id)
            if not user or user.paused:
                return
            
            keyboard = [
                [InlineKeyboardButton("Ответить", callback_data=f"respond_{user_id}")],
                [InlineKeyboardButton("Отложить на 15 мин", callback_data=f"snooze_{user_id}")],
                [InlineKeyboardButton("Пропустить сегодня", callback_data=f"skip_{user_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Simple hardcoded text instead of importing
            ping_text = """🌟 Как ты сейчас?

Если хочется — выбери 1-2 слова или просто опиши своими словами.

<i>Сам факт, что ты это заметишь и назовёшь, — уже шаг к ясности.</i>"""
            
            await bot.send_message(
                chat_id=user.chat_id,
                text=ping_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            
            logger.info(f"Sent emotion ping to user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to send ping to user {user_id}: {e}")
    
    async def schedule_snooze(self, user_id: int, minutes: int = 15):
        """Schedule a snoozed ping"""
        if not self.scheduler:
            return
            
        snooze_time = datetime.now() + timedelta(minutes=minutes)
        job_id = f'snooze_{user_id}_{int(snooze_time.timestamp())}'
        
        self.scheduler.add_job(
            self._send_simple_ping,
            'date',
            run_date=snooze_time,
            args=[user_id],
            id=job_id,
            replace_existing=True
        )
        
        logger.info(f"Scheduled snooze ping for user {user_id} in {minutes} minutes")
    
    async def skip_today(self, user_id: int):
        """Skip remaining pings for today"""
        if not self.scheduler:
            return
            
        import zoneinfo
        user = self.db.get_user(user_id)
        if not user:
            return
            
        tz = zoneinfo.ZoneInfo(user.timezone)
        today_str = datetime.now(tz).strftime('%Y%m%d')
        
        # Remove all remaining ping jobs for today
        for i in range(self.DAILY_PINGS):
            job_id = f'ping_{user_id}_{today_str}_{i}'
            try:
                self.scheduler.remove_job(job_id)
            except:
                pass
        
        logger.info(f"Skipped remaining pings for user {user_id} today")
    
    async def stop(self):
        """Stop the scheduler"""
        if self.scheduler:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")


def test_random_time_generation():
    """Unit test for random time generation algorithm"""
    scheduler = RandomScheduler(None)
    
    success_count = 0
    total_tests = 1000
    
    for i in range(total_tests):
        times = scheduler.generate_random_times()
        
        # Test conditions
        if (len(times) == 4 and 
            scheduler.validate_time_spacing(times) and
            all(9 <= t.hour < 23 for t in times)):
            success_count += 1
        else:
            print(f"Test {i+1} failed: {[t.strftime('%H:%M') for t in times]}")
    
    success_rate = success_count / total_tests * 100
    print(f"Random time generation test: {success_count}/{total_tests} ({success_rate:.1f}%) passed")
    
    if success_rate < 95:
        raise Exception(f"Random time generation test failed: only {success_rate:.1f}% success rate")
    
    return True


if __name__ == "__main__":
    # Run unit test
    test_random_time_generation()
    print("All tests passed!")
