#!/usr/bin/env python3
"""
Fixed Scheduler for EmoJournal Bot - Enhanced with timezone-aware weekly summaries
Generates 4 fixed daily slots at 9, 13, 17, 21 hours + weekly summaries per user timezone
"""

import logging
import asyncio
from datetime import datetime, timedelta, time
from typing import List, Optional
import json
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

logger = logging.getLogger(__name__)

class FixedScheduler:
    """Handles fixed emotion ping scheduling + timezone-aware weekly summaries with enhanced error handling"""
    
    # Configuration constants
    FIXED_HOURS = [9, 13, 17, 21]  # 4 раза в день: 9:00, 13:00, 17:00, 21:00
    DEFAULT_SUMMARY_HOUR = 21  # По умолчанию воскресенье в 21:00
    MAX_RETRIES = 3
    RETRY_DELAY = 60  # seconds
    
    def __init__(self, db):
        self.db = db
        self.scheduler = None
        self.running = False
        
    async def start(self):
        """Initialize and start the scheduler with error handling"""
        if self.running:
            logger.warning("Scheduler already running")
            return
        
        try:
            # Simplified scheduler configuration
            jobstores = {
                'default': MemoryJobStore()
            }
            
            executors = {
                'default': AsyncIOExecutor()
            }
            
            job_defaults = {
                'coalesce': False,
                'max_instances': 3,
                'misfire_grace_time': 30
            }
            
            self.scheduler = AsyncIOScheduler(
                jobstores=jobstores,
                executors=executors,
                job_defaults=job_defaults,
                timezone='UTC'  # Use UTC as base, handle user timezones manually
            )
            
            # Add event listeners for error handling
            self.scheduler.add_listener(self._job_error_listener, EVENT_JOB_ERROR)
            self.scheduler.add_listener(self._job_executed_listener, EVENT_JOB_EXECUTED)
            
            self.scheduler.start()
            self.running = True
            
            # Schedule daily schedule generation for all active users
            self.scheduler.add_job(
                self._daily_schedule_all_users_safe,
                'cron',
                hour=23,  # UTC 23:00 = Moscow 02:00, before most users' day starts
                minute=55,
                id='daily_schedule_generator',
                replace_existing=True
            )
            
            # NEW: Schedule weekly summary jobs for all users (runs hourly to check timezones)
            self.scheduler.add_job(
                self._check_weekly_summaries_safe,
                'cron',
                minute=0,  # Every hour at minute 0
                id='weekly_summaries_checker',
                replace_existing=True
            )
            
            logger.info("Fixed scheduler started successfully with timezone-aware weekly summaries")
            
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
            self.running = False
            raise
    
    def _job_error_listener(self, event):
        """Handle job execution errors"""
        logger.error(f"Job {event.job_id} crashed: {event.exception}")
        
        # Attempt to reschedule failed ping jobs
        if event.job_id.startswith('ping_'):
            try:
                parts = event.job_id.split('_')
                if len(parts) >= 2:
                    user_id = int(parts[1])
                    asyncio.create_task(self._retry_failed_ping(user_id))
            except (ValueError, IndexError):
                pass
    
    def _job_executed_listener(self, event):
        """Log successful job executions"""
        if event.job_id.startswith('ping_') or 'summaries' in event.job_id:
            logger.debug(f"Successfully executed job {event.job_id}")
    
    async def _retry_failed_ping(self, user_id: int):
        """Retry failed ping with delay"""
        try:
            await asyncio.sleep(self.RETRY_DELAY)
            await self._send_simple_ping(user_id)
            logger.info(f"Successfully retried ping for user {user_id}")
        except Exception as e:
            logger.error(f"Retry ping failed for user {user_id}: {e}")
    
    async def _check_weekly_summaries_safe(self):
        """Safely check if any users need weekly summaries (runs hourly)"""
        try:
            await self._check_weekly_summaries()
        except Exception as e:
            logger.error(f"Failed to check weekly summaries: {e}")
    
    async def _check_weekly_summaries(self):
        """Check if any users need weekly summaries based on their timezone and settings"""
        try:
            # Get all active users
            active_users = self.db.get_active_users()
            
            current_utc = datetime.now()
            users_to_send = []
            
            for user in active_users:
                if user.paused:
                    continue
                
                try:
                    # Get user settings
                    user_settings = self.db.get_user_settings(user.id)
                    if not user_settings or not user_settings.get('weekly_summary_enabled', True):
                        continue
                    
                    summary_hour = user_settings.get('summary_time_hour', self.DEFAULT_SUMMARY_HOUR)
                    
                    # Convert to user's timezone
                    import zoneinfo
                    try:
                        user_tz = zoneinfo.ZoneInfo(user.timezone)
                    except Exception:
                        user_tz = zoneinfo.ZoneInfo('Europe/Moscow')
                        logger.warning(f"Invalid timezone for user {user.id}, using Europe/Moscow")
                    
                    user_time = current_utc.replace(tzinfo=zoneinfo.ZoneInfo('UTC')).astimezone(user_tz)
                    
                    # Check if it's Sunday at the right hour for this user
                    if (user_time.weekday() == 6 and  # Sunday = 6
                        user_time.hour == summary_hour and
                        user_time.minute < 30):  # Only in first 30 minutes of the hour
                        
                        # Check if we already sent summary today (avoid duplicates)
                        if not self._already_sent_summary_today(user.id, user_time.date()):
                            users_to_send.append(user)
                    
                except Exception as e:
                    logger.error(f"Error checking weekly summary for user {user.id}: {e}")
            
            # Send summaries to eligible users
            if users_to_send:
                await self._send_weekly_summaries_to_users(users_to_send)
                
        except Exception as e:
            logger.error(f"Error in weekly summaries checker: {e}")
    
    def _already_sent_summary_today(self, user_id: int, date_local) -> bool:
        """Check if we already sent a summary to user today (simple in-memory tracking)"""
        # For production, you might want to store this in database
        # For now, use a simple approach - check if user had recent activity
        if not hasattr(self, '_sent_summaries'):
            self._sent_summaries = set()
        
        key = f"{user_id}_{date_local}"
        if key in self._sent_summaries:
            return True
        
        # Mark as sent (cleanup old entries periodically)
        self._sent_summaries.add(key)
        
        # Simple cleanup: remove entries older than 7 days
        if len(self._sent_summaries) > 1000:  # Arbitrary limit
            self._sent_summaries.clear()
            logger.info("Cleared old summary send tracking")
        
        return False
    
    async def _send_weekly_summaries_to_users(self, users: list):
        """Send weekly summaries to list of users"""
        success_count = 0
        error_count = 0
        
        for user in users:
            try:
                # Check if user has entries for the week
                entries = self.db.get_user_entries(user.id, days=7)
                if len(entries) == 0:
                    logger.debug(f"No entries for user {user.id}, skipping weekly summary")
                    continue
                
                # Send summary
                await self._send_weekly_summary_to_user(user.id, user.chat_id, user.timezone)
                success_count += 1
                
                # Small delay between sends to avoid hitting rate limits
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Failed to send weekly summary to user {user.id}: {e}")
                error_count += 1
        
        if success_count > 0 or error_count > 0:
            logger.info(f"Weekly summaries sent: {success_count} success, {error_count} errors")
    
    async def _send_weekly_summary_to_user(self, user_id: int, chat_id: int, user_timezone: str):
        """Send weekly summary to specific user"""
        try:
            from .analysis import WeeklyAnalyzer
            from .i18n import Texts
            
            # Create analyzer and generate summary
            analyzer = WeeklyAnalyzer(self.db)
            summary = await analyzer.generate_summary(user_id, days=7)
            
            texts = Texts()
            
            # Add header for automatic summary
            auto_summary = f"{texts.AUTO_SUMMARY_HEADER}\n\n{summary}"
            
            # Send via Telegram API
            bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
            if not bot_token:
                logger.error("TELEGRAM_BOT_TOKEN not set")
                return
            
            from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
            bot = Bot(token=bot_token)
            
            # Add buttons after summary
            keyboard = [
                [InlineKeyboardButton("📊 Другой период", callback_data="summary_period_custom")],
                [InlineKeyboardButton("📥 Экспорт CSV", callback_data="export_csv_inline")],
                [InlineKeyboardButton("⚙️ Настройки", callback_data="toggle_weekly_summary")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await bot.send_message(
                chat_id=chat_id,
                text=auto_summary,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            
            logger.info(f"Sent automatic weekly summary to user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to send weekly summary to user {user_id}: {e}")
            raise
    
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
        """Start daily scheduling for a specific user with error handling"""
        if not self.scheduler or not self.running:
            logger.warning("Scheduler not running, cannot start user schedule")
            return
        
        try:
            user = self.db.get_user(user_id)
            if not user or user.paused:
                logger.info(f"User {user_id} is paused or not found, skipping schedule")
                return
            
            # Remove existing jobs for this user
            await self.stop_user_schedule(user_id)
            
            # Generate today's schedule if not exists or incomplete
            await self._ensure_todays_schedule_safe(user_id, user.timezone)
            
            # Schedule daily regeneration (in user's timezone)
            import zoneinfo
            try:
                user_tz = zoneinfo.ZoneInfo(user.timezone)
            except Exception:
                user_tz = zoneinfo.ZoneInfo('Europe/Moscow')
                logger.warning(f"Invalid timezone for user {user_id}, using Europe/Moscow")
            
            # Schedule at 8:55 in user's timezone
            self.scheduler.add_job(
                self._generate_user_daily_schedule_safe,
                'cron',
                hour=8,
                minute=55,
                args=[user_id],
                id=f'daily_schedule_{user_id}',
                timezone=user.timezone,
                replace_existing=True
            )
            
            logger.info(f"Started scheduling for user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to start user schedule for {user_id}: {e}")
    
    async def stop_user_schedule(self, user_id: int):
        """Stop scheduling for a user with error handling"""
        if not self.scheduler:
            return
        
        try:
            # Remove daily schedule job
            try:
                self.scheduler.remove_job(f'daily_schedule_{user_id}')
            except Exception:
                pass  # Job might not exist
            
            # Remove today's ping jobs
            today_str = datetime.now().strftime('%Y%m%d')
            for hour in self.FIXED_HOURS:
                try:
                    self.scheduler.remove_job(f'ping_{user_id}_{today_str}_{hour}')
                except Exception:
                    pass  # Job might not exist
            
            logger.info(f"Stopped scheduling for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error stopping user schedule for {user_id}: {e}")
    
    async def _ensure_todays_schedule_safe(self, user_id: int, user_timezone: str = 'Europe/Moscow'):
        """Safely ensure today's schedule exists"""
        try:
            await self._ensure_todays_schedule(user_id, user_timezone)
        except Exception as e:
            logger.error(f"Failed to ensure today's schedule for user {user_id}: {e}")
    
    async def _ensure_todays_schedule(self, user_id: int, user_timezone: str = 'Europe/Moscow'):
        """Ensure today's schedule exists and create missing ping jobs"""
        import zoneinfo
        
        try:
            tz = zoneinfo.ZoneInfo(user_timezone)
        except Exception:
            tz = zoneinfo.ZoneInfo('Europe/Moscow')
            logger.warning(f"Invalid timezone {user_timezone}, using Europe/Moscow")
        
        now = datetime.now(tz)
        today = now.date()
        
        # Generate fixed times
        times = self.generate_fixed_times()
        times_json = json.dumps([t.strftime('%H:%M') for t in times])
        
        # Save schedule to database (always overwrite for consistency)
        try:
            self.db.save_user_schedule(user_id, today, times_json)
        except Exception as e:
            logger.error(f"Failed to save schedule for user {user_id}: {e}")
            return
        
        # Create ping jobs for remaining slots (future times only)
        today_str = today.strftime('%Y%m%d')
        
        for ping_time in times:
            ping_datetime = datetime.combine(today, ping_time, tzinfo=tz)
            
            # Only schedule if time is in the future
            if ping_datetime > now:
                job_id = f'ping_{user_id}_{today_str}_{ping_time.hour}'
                
                # Remove existing job if any
                try:
                    self.scheduler.remove_job(job_id)
                except Exception:
                    pass
                
                # Schedule ping
                try:
                    self.scheduler.add_job(
                        self._send_simple_ping_safe,
                        'date',
                        run_date=ping_datetime,
                        args=[user_id],
                        id=job_id,
                        replace_existing=True
                    )
                    
                    logger.debug(f"Scheduled ping for user {user_id} at {ping_datetime}")
                except Exception as e:
                    logger.error(f"Failed to schedule ping for user {user_id}: {e}")
    
    async def _generate_user_daily_schedule_safe(self, user_id: int):
        """Safely generate and schedule pings for a specific user"""
        try:
            await self._generate_user_daily_schedule(user_id)
        except Exception as e:
            logger.error(f"Failed to generate daily schedule for user {user_id}: {e}")
    
    async def _generate_user_daily_schedule(self, user_id: int):
        """Generate and schedule pings for a specific user (called daily at 08:55)"""
        user = self.db.get_user(user_id)
        if not user or user.paused:
            return
        
        import zoneinfo
        try:
            tz = zoneinfo.ZoneInfo(user.timezone)
        except Exception:
            tz = zoneinfo.ZoneInfo('Europe/Moscow')
            logger.warning(f"Invalid timezone for user {user_id}, using Europe/Moscow")
        
        tomorrow = (datetime.now(tz) + timedelta(days=1)).date()
        
        # Generate fixed times for tomorrow
        times = self.generate_fixed_times()
        times_json = json.dumps([t.strftime('%H:%M') for t in times])
        
        # Save schedule to database
        try:
            self.db.save_user_schedule(user_id, tomorrow, times_json)
        except Exception as e:
            logger.error(f"Failed to save schedule for user {user_id}: {e}")
            return
        
        # Schedule ping jobs for tomorrow
        tomorrow_str = tomorrow.strftime('%Y%m%d')
        
        for ping_time in times:
            ping_datetime = datetime.combine(tomorrow, ping_time, tzinfo=tz)
            job_id = f'ping_{user_id}_{tomorrow_str}_{ping_time.hour}'
            
            try:
                self.scheduler.add_job(
                    self._send_simple_ping_safe,
                    'date',
                    run_date=ping_datetime,
                    args=[user_id],
                    id=job_id,
                    replace_existing=True
                )
            except Exception as e:
                logger.error(f"Failed to schedule ping job {job_id}: {e}")
        
        logger.info(f"Generated schedule for user {user_id} on {tomorrow}: {[t.strftime('%H:%M') for t in times]}")
    
    async def _daily_schedule_all_users_safe(self):
        """Safely generate schedules for all active users"""
        try:
            await self._daily_schedule_all_users()
        except Exception as e:
            logger.error(f"Failed to generate daily schedules for all users: {e}")
    
    async def _daily_schedule_all_users(self):
        """Generate schedules for all active users (runs daily at 23:55 UTC)"""
        try:
            active_users = self.db.get_active_users()
        except Exception as e:
            logger.error(f"Failed to get active users: {e}")
            return
        
        success_count = 0
        error_count = 0
        
        for user in active_users:
            if not user.paused:
                try:
                    await self._generate_user_daily_schedule(user.id)
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to generate schedule for user {user.id}: {e}")
                    error_count += 1
        
        logger.info(f"Generated daily schedules: {success_count} success, {error_count} errors")
    
    async def _send_simple_ping_safe(self, user_id: int):
        """Safely send ping with comprehensive error handling"""
        try:
            await self._send_simple_ping(user_id)
        except Exception as e:
            logger.error(f"Failed to send ping to user {user_id}: {e}")
            # Don't re-raise to prevent scheduler from stopping
    
    async def _send_simple_ping(self, user_id: int):
        """Send emotion ping to user with enhanced error handling"""
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not bot_token:
            logger.error("TELEGRAM_BOT_TOKEN not set")
            return
        
        try:
            from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
            from telegram.error import TelegramError, Forbidden, ChatNotFound
            
            bot = Bot(token=bot_token)
            
            # Check if user still exists and is not paused
            user = self.db.get_user(user_id)
            if not user or user.paused:
                logger.info(f"User {user_id} is paused or not found, skipping ping")
                return
            
            keyboard = [
                [InlineKeyboardButton("Ответить", callback_data=f"respond_{user_id}")],
                [InlineKeyboardButton("Отложить на 15 мин", callback_data=f"snooze_{user_id}")],
                [InlineKeyboardButton("Пропустить сегодня", callback_data=f"skip_{user_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
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
            
        except Forbidden:
            logger.warning(f"Bot was blocked by user {user_id}")
            # Automatically pause user notifications
            try:
                self.db.update_user_paused(user_id, True)
            except Exception:
                pass
        except ChatNotFound:
            logger.warning(f"Chat not found for user {user_id}")
            # Automatically pause user notifications
            try:
                self.db.update_user_paused(user_id, True)
            except Exception:
                pass
        except TelegramError as e:
            logger.error(f"Telegram API error sending ping to user {user_id}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error sending ping to user {user_id}: {e}")
    
    async def schedule_snooze(self, user_id: int, minutes: int = 15):
        """Schedule a snoozed ping with validation"""
        if not self.scheduler or not self.running:
            logger.warning("Scheduler not running, cannot schedule snooze")
            return
        
        # Validate inputs
        if not isinstance(user_id, int) or user_id <= 0:
            logger.error(f"Invalid user_id for snooze: {user_id}")
            return
        
        if not isinstance(minutes, int) or minutes <= 0 or minutes > 120:
            minutes = 15  # Default to 15 minutes, max 2 hours
        
        try:
            snooze_time = datetime.now() + timedelta(minutes=minutes)
            job_id = f'snooze_{user_id}_{int(snooze_time.timestamp())}'
            
            self.scheduler.add_job(
                self._send_simple_ping_safe,
                'date',
                run_date=snooze_time,
                args=[user_id],
                id=job_id,
                replace_existing=True
            )
            
            logger.info(f"Scheduled snooze ping for user {user_id} in {minutes} minutes")
            
        except Exception as e:
            logger.error(f"Failed to schedule snooze for user {user_id}: {e}")
    
    async def skip_today(self, user_id: int):
        """Skip remaining pings for today with validation"""
        if not self.scheduler:
            return
        
        if not isinstance(user_id, int) or user_id <= 0:
            logger.error(f"Invalid user_id for skip_today: {user_id}")
            return
        
        try:
            user = self.db.get_user(user_id)
            if not user:
                logger.warning(f"User {user_id} not found for skip_today")
                return
            
            import zoneinfo
            try:
                tz = zoneinfo.ZoneInfo(user.timezone)
            except Exception:
                tz = zoneinfo.ZoneInfo('Europe/Moscow')
            
            today_str = datetime.now(tz).strftime('%Y%m%d')
            
            # Remove all remaining ping jobs for today
            removed_count = 0
            for hour in self.FIXED_HOURS:
                job_id = f'ping_{user_id}_{today_str}_{hour}'
                try:
                    self.scheduler.remove_job(job_id)
                    removed_count += 1
                except Exception:
                    pass  # Job might not exist
            
            logger.info(f"Skipped {removed_count} remaining pings for user {user_id} today")
            
        except Exception as e:
            logger.error(f"Failed to skip today for user {user_id}: {e}")
    
    async def stop(self):
        """Stop the scheduler safely"""
        if self.scheduler and self.running:
            try:
                self.scheduler.shutdown(wait=False)
                self.running = False
                logger.info("Scheduler stopped successfully")
            except Exception as e:
                logger.error(f"Error stopping scheduler: {e}")
        else:
            logger.info("Scheduler was not running")
    
    def get_scheduler_status(self) -> dict:
        """Get scheduler status information"""
        if not self.scheduler:
            return {"running": False, "jobs": 0}
        
        try:
            jobs = self.scheduler.get_jobs()
            return {
                "running": self.running,
                "jobs": len(jobs),
                "job_details": [
                    {
                        "id": job.id,
                        "next_run": job.next_run_time.isoformat() if job.next_run_time else None
                    }
                    for job in jobs[:10]  # Limit to first 10 jobs
                ]
            }
        except Exception as e:
            logger.error(f"Error getting scheduler status: {e}")
            return {"running": self.running, "jobs": 0, "error": str(e)}
    
    async def reschedule_user_if_needed(self, user_id: int):
        """Reschedule user if they have no upcoming pings"""
        if not self.scheduler or not self.running:
            return
        
        try:
            # Check if user has any scheduled jobs
            jobs = self.scheduler.get_jobs()
            user_jobs = [job for job in jobs if job.id.startswith(f'ping_{user_id}_')]
            
            if not user_jobs:
                logger.info(f"No scheduled jobs found for user {user_id}, rescheduling")
                await self.start_user_schedule(user_id)
            
        except Exception as e:
            logger.error(f"Error checking/rescheduling user {user_id}: {e}")

    # NEW: Manual trigger for testing weekly summaries
    async def send_test_weekly_summary(self, user_id: int):
        """Send a test weekly summary to a specific user (for debugging)"""
        try:
            user = self.db.get_user(user_id)
            if not user:
                logger.error(f"User {user_id} not found for test summary")
                return False
            
            # Check if user has entries
            entries = self.db.get_user_entries(user_id, days=7)
            if len(entries) == 0:
                logger.info(f"No entries for user {user_id}, cannot send test summary")
                return False
            
            await self._send_weekly_summary_to_user(user_id, user.chat_id, user.timezone)
            return True
            
        except Exception as e:
            logger.error(f"Failed to send test weekly summary to user {user_id}: {e}")
            return False

    # NEW: Get users due for weekly summary (for debugging)
    def get_users_due_for_summary(self) -> list:
        """Get list of users who are due for weekly summary right now"""
        try:
            active_users = self.db.get_active_users()
            current_utc = datetime.now()
            due_users = []
            
            for user in active_users:
                if user.paused:
                    continue
                
                try:
                    user_settings = self.db.get_user_settings(user.id)
                    if not user_settings or not user_settings.get('weekly_summary_enabled', True):
                        continue
                    
                    summary_hour = user_settings.get('summary_time_hour', self.DEFAULT_SUMMARY_HOUR)
                    
                    import zoneinfo
                    try:
                        user_tz = zoneinfo.ZoneInfo(user.timezone)
                    except Exception:
                        user_tz = zoneinfo.ZoneInfo('Europe/Moscow')
                    
                    user_time = current_utc.replace(tzinfo=zoneinfo.ZoneInfo('UTC')).astimezone(user_tz)
                    
                    if user_time.weekday() == 6 and user_time.hour == summary_hour:
                        entries = self.db.get_user_entries(user.id, days=7)
                        if len(entries) > 0:
                            due_users.append({
                                'user_id': user.id,
                                'chat_id': user.chat_id,
                                'timezone': user.timezone,
                                'local_time': user_time.strftime('%Y-%m-%d %H:%M'),
                                'entries_count': len(entries)
                            })
                
                except Exception as e:
                    logger.error(f"Error checking user {user.id} for summary: {e}")
            
            return due_users
            
        except Exception as e:
            logger.error(f"Error getting users due for summary: {e}")
            return []


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


def test_timezone_summary_logic():
    """Test timezone-aware weekly summary logic"""
    from datetime import datetime
    import zoneinfo
    
    # Test different timezones at Sunday 21:00
    test_timezones = ['Europe/Moscow', 'Asia/Yekaterinburg', 'Europe/London', 'America/New_York']
    
    for tz_name in test_timezones:
        try:
            tz = zoneinfo.ZoneInfo(tz_name)
            
            # Create a Sunday 21:00 in this timezone
            sunday_21 = datetime(2024, 1, 7, 21, 0, 0, tzinfo=tz)  # A Sunday
            
            # Convert to UTC
            utc_time = sunday_21.astimezone(zoneinfo.ZoneInfo('UTC'))
            
            print(f"{tz_name}: Sunday 21:00 = {utc_time.strftime('%Y-%m-%d %H:%M UTC')}")
            
        except Exception as e:
            print(f"Error testing timezone {tz_name}: {e}")
    
    print("Timezone summary logic test completed")


if __name__ == "__main__":
    # Run unit tests
    test_fixed_time_generation()
    test_timezone_summary_logic()
    print("All scheduler tests passed!")
