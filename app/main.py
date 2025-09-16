#!/usr/bin/env python3
"""
EmoJournal Telegram Bot - Main Application
FIXED: Enhanced webhook handling with detailed logging and proper setup
"""

import logging
import os
import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from collections import defaultdict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from telegram.error import TelegramError

from .db import Database, User, Entry
from .scheduler import FixedScheduler
from .i18n import Texts
from .analysis import WeeklyAnalyzer
from .security import sanitize_user_input, InputValidator
from .rate_limiter import check_user_limits, command_rate_limiter

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ WEBHOOK
logging.getLogger("telegram").setLevel(logging.DEBUG)
logging.getLogger("httpx").setLevel(logging.INFO)
logging.getLogger("aiohttp").setLevel(logging.INFO)

class UserStateManager:
    """Простое управление состояниями пользователей с автоочисткой"""
    
    def __init__(self, cleanup_interval: int = 3600):  # 1 час
        self.states: Dict[int, Dict[str, Any]] = {}
        self.cleanup_interval = cleanup_interval
        self.last_cleanup = time.time()
    
    def set_state(self, user_id: int, state: str, data: Dict[str, Any] = None):
        """Установить состояние пользователя"""
        self._cleanup_if_needed()
        
        if user_id not in self.states:
            self.states[user_id] = {}
        
        self.states[user_id].update({
            'state': state,
            'timestamp': time.time(),
            **(data or {})
        })
    
    def get_state(self, user_id: int) -> Dict[str, Any]:
        """Получить состояние пользователя"""
        self._cleanup_if_needed()
        
        user_state = self.states.get(user_id, {})
        
        # Проверить не устарело ли состояние (24 часа)
        if user_state.get('timestamp', 0) < time.time() - 86400:
            self.clear_state(user_id)
            return {}
        
        return user_state
    
    def clear_state(self, user_id: int):
        """Очистить состояние пользователя"""
        if user_id in self.states:
            del self.states[user_id]
    
    def _cleanup_if_needed(self):
        """Периодическая очистка устаревших состояний"""
        now = time.time()
        if now - self.last_cleanup < self.cleanup_interval:
            return
        
        cutoff_time = now - 86400  # 24 часа
        expired_users = [
            user_id for user_id, state in self.states.items()
            if state.get('timestamp', 0) < cutoff_time
        ]
        
        for user_id in expired_users:
            del self.states[user_id]
        
        self.last_cleanup = now
        
        if expired_users:
            logger.info(f"Cleaned up {len(expired_users)} expired user states")


class EmoJournalBot:
    def __init__(self):
        self.db = Database()
        
        # ИСПРАВЛЕНИЕ: Обратная совместимость с scheduler
        try:
            # Пробуем новый способ с bot_instance
            self.scheduler = FixedScheduler(self.db, bot_instance=self)
            logger.info("Scheduler initialized with bot_instance")
        except TypeError:
            # Fallback на старый способ
            self.scheduler = FixedScheduler(self.db)
            logger.info("Scheduler initialized in legacy mode")
            # Устанавливаем bot_instance вручную
            self.scheduler.bot_instance = self
        
        self.texts = Texts()
        self.analyzer = WeeklyAnalyzer(self.db)
        
        # Безопасное управление состояниями
        self.user_state_manager = UserStateManager()
        
        # Environment validation
        self.bot_token = self._get_env_var('TELEGRAM_BOT_TOKEN')
        self.webhook_url = self._get_env_var('WEBHOOK_URL')
        self.port = int(os.getenv('PORT', '10000'))
        
        # Создаем Bot instance для scheduler
        self.bot = Bot(token=self.bot_token)
    
    def _get_env_var(self, name: str) -> str:
        value = os.getenv(name)
        if not value:
            logger.error(f"Required environment variable {name} not set")
            raise ValueError(f"Environment variable {name} is required")
        return value
    
    def _set_user_state(self, user_id: int, state: str, data: Dict[str, Any] = None):
        """Set user conversation state"""
        self.user_state_manager.set_state(user_id, state, data)
    
    def _get_user_state(self, user_id: int) -> Dict[str, Any]:
        """Get user conversation state"""
        return self.user_state_manager.get_state(user_id)
    
    def _clear_user_state(self, user_id: int):
        """Clear user conversation state"""
        self.user_state_manager.clear_state(user_id)
    
    async def _check_rate_limits(self, update: Update, command: str = "") -> bool:
        """Проверить rate limits и отправить сообщение если превышен"""
        user_id = update.effective_user.id
        message_text = getattr(update.message, 'text', '') if update.message else ''
        
        allowed, reason = check_user_limits(user_id, message_text, command)
        
        if not allowed:
            if update.message:
                await update.message.reply_text(reason)
            elif update.callback_query:
                await update.callback_query.answer(reason, show_alert=True)
            return False
        
        return True
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command with updated onboarding"""
        if not await self._check_rate_limits(update, 'start'):
            return
            
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        logger.info(f"Received /start from user {user_id}")
        
        # Clear any existing state
        self._clear_user_state(user_id)
        
        try:
            # Create or get user
            user = self.db.get_user(user_id)
            if not user:
                user = self.db.create_user(user_id, chat_id)
                logger.info(f"Created new user {user_id}")
                
                # Запускаем scheduler для нового пользователя
                try:
                    await self.scheduler.start_user_schedule(user_id)
                    logger.info(f"Started scheduling for new user {user_id}")
                except Exception as e:
                    logger.error(f"Failed to start scheduling for user {user_id}: {e}")
            else:
                logger.info(f"Existing user {user_id} started bot")
                
                # Для существующих пользователей тоже проверяем scheduling
                try:
                    await self.scheduler.start_user_schedule(user_id)
                    logger.info(f"Restarted scheduling for existing user {user_id}")
                except Exception as e:
                    logger.error(f"Failed to restart scheduling for user {user_id}: {e}")
            
            # Set bot commands menu (только один раз)
            if not hasattr(self, '_commands_set'):
                commands = [
                    BotCommand("start", "🎭 Запустить бота"),
                    BotCommand("note", "📝 Записать эмоцию сейчас"),
                    BotCommand("help", "❓ Помощь и информация"),
                    BotCommand("summary", "📊 Сводка за период"),
                    BotCommand("settings", "⚙️ Настройки бота"),
                    BotCommand("export", "📥 Экспорт данных в CSV"),
                    BotCommand("timezone", "🌍 Настройка часового пояса"),
                    BotCommand("pause", "⏸️ Приостановить уведомления"),
                    BotCommand("resume", "▶️ Возобновить уведомления"),
                    BotCommand("stats", "📈 Статистика бота"),
                    BotCommand("delete_me", "🗑️ Удалить все данные")
                ]
                
                # Устанавливаем команды асинхронно
                asyncio.create_task(context.bot.set_my_commands(commands))
                self._commands_set = True
                logger.info("Set bot commands menu")
            
            # Моментальный ответ пользователю
            await update.message.reply_text(
                self.texts.ONBOARDING,
                parse_mode='HTML'
            )
            logger.info(f"Sent onboarding message to user {user_id}")
            
        except Exception as e:
            logger.error(f"Error in start command for user {user_id}: {e}")
            await update.message.reply_text(
                "Произошла ошибка при запуске. Попробуйте позже."
            )
    
    async def note_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /note command for manual emotion entry"""
        if not await self._check_rate_limits(update, 'note'):
            return
            
        user_id = update.effective_user.id
        logger.info(f"Received /note from user {user_id}")
        self._clear_user_state(user_id)
        
        keyboard = [
            [InlineKeyboardButton("Показать идеи эмоций", callback_data="show_emotions")],
            [InlineKeyboardButton("Напишу сам(а)", callback_data="other_emotion")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📝 Записать эмоцию сейчас\n\n" + self.texts.EMOTION_QUESTION,
            reply_markup=reply_markup
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        if not await self._check_rate_limits(update, 'help'):
            return
            
        user_id = update.effective_user.id
        logger.info(f"Received /help from user {user_id}")
        
        await update.message.reply_text(
            self.texts.HELP,
            parse_mode='HTML'
        )
    
    async def timezone_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /timezone command"""
        if not await self._check_rate_limits(update, 'timezone'):
            return
            
        user_id = update.effective_user.id
        logger.info(f"Received /timezone from user {user_id}")
        
        if context.args:
            tz_name = ' '.join(context.args)
            
            # Валидация timezone
            tz_validated = sanitize_user_input(tz_name, "general")
            if not tz_validated:
                await update.message.reply_text(
                    "Неверный формат часового пояса. Используйте формат IANA, например: Europe/Moscow"
                )
                return
                
            try:
                import zoneinfo
                zoneinfo.ZoneInfo(tz_validated)  # Validate timezone
                self.db.update_user_timezone(user_id, tz_validated)
                await update.message.reply_text(
                    f"Часовой пояс установлен: {tz_validated}"
                )
                # Перезапускаем scheduling с новым timezone
                try:
                    await self.scheduler.start_user_schedule(user_id)
                    logger.info(f"Restarted scheduling for user {user_id} with new timezone")
                except Exception as e:
                    logger.error(f"Failed to restart scheduling after timezone change: {e}")
            except Exception:
                await update.message.reply_text(
                    "Неверный часовой пояс. Используйте формат IANA, например: Europe/Moscow, Asia/Yekaterinburg"
                )
        else:
            user = self.db.get_user(user_id)
            current_tz = user.timezone if user else "Europe/Moscow"
            await update.message.reply_text(
                f"Текущий часовой пояс: {current_tz}\n\n"
                "Для изменения используйте: /timezone Europe/Moscow"
            )
    
    async def summary_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /summary command - now shows interactive period selection"""
        if not await self._check_rate_limits(update, 'summary'):
            return
            
        user_id = update.effective_user.id
        logger.info(f"Received /summary from user {user_id}")
        self._clear_user_state(user_id)
        
        # Show period selection buttons
        keyboard = [
            [
                InlineKeyboardButton("7 дней", callback_data="summary_period_7"),
                InlineKeyboardButton("2 недели", callback_data="summary_period_14")
            ],
            [
                InlineKeyboardButton("30 дней", callback_data="summary_period_30"),
                InlineKeyboardButton("3 месяца", callback_data="summary_period_90")
            ],
            [
                InlineKeyboardButton("Другой период", callback_data="summary_period_custom")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📊 За какой период показать сводку?",
            reply_markup=reply_markup
        )
    
    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /settings command - user preferences"""
        if not await self._check_rate_limits(update, 'settings'):
            return
            
        user_id = update.effective_user.id
        logger.info(f"Received /settings from user {user_id}")
        
        try:
            # Get current settings
            settings = self.db.get_user_settings(user_id)
            if not settings:
                # Create default settings if not exist
                self.db.update_user_settings(user_id, 
                    weekly_summary_enabled=True, 
                    summary_time_hour=21
                )
                settings = self.db.get_user_settings(user_id)
            
            weekly_enabled = settings.get('weekly_summary_enabled', True)
            summary_hour = settings.get('summary_time_hour', 21)
            
            # Create settings keyboard
            weekly_text = "✅ Включены" if weekly_enabled else "❌ Отключены"
            keyboard = [
                [InlineKeyboardButton(f"Еженедельные саммари: {weekly_text}", 
                                    callback_data="toggle_weekly_summary")],
                [InlineKeyboardButton(f"Время отправки: {summary_hour:02d}:00", 
                                    callback_data="change_summary_time")],
                [InlineKeyboardButton("💾 Сохранить и закрыть", 
                                    callback_data="settings_close")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "⚙️ <b>Настройки EmoJournal</b>\n\n"
                f"📅 <b>Автоматические саммари:</b> {weekly_text}\n"
                f"🕘 <b>Время отправки:</b> каждое воскресенье в {summary_hour:02d}:00\n\n"
                "Выберите что хотите изменить:",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error(f"Error in settings command for user {user_id}: {e}")
            await update.message.reply_text("Произошла ошибка при загрузке настроек.")
    
    async def export_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /export command"""
        if not await self._check_rate_limits(update, 'export'):
            return
            
        user_id = update.effective_user.id
        logger.info(f"Received /export from user {user_id}")
        
        try:
            csv_data = await self.analyzer.export_csv(user_id)
            
            if csv_data:
                import io
                csv_file = io.BytesIO(csv_data.encode('utf-8'))
                csv_file.name = f"emojournal_export_{datetime.now().strftime('%Y%m%d')}.csv"
                
                await update.message.reply_document(
                    document=csv_file,
                    caption="Ваши данные в формате CSV"
                )
            else:
                await update.message.reply_text("Пока нет данных для экспорта")
                
        except Exception as e:
            logger.error(f"Error exporting data for user {user_id}: {e}")
            await update.message.reply_text(
                "Не удалось экспортировать данные. Попробуйте позже."
            )
    
    async def delete_me_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /delete_me command"""
        if not await self._check_rate_limits(update, 'delete_me'):
            return
            
        user_id = update.effective_user.id
        logger.info(f"Received /delete_me from user {user_id}")
        
        keyboard = [
            [InlineKeyboardButton("Да, удалить все мои данные", callback_data=f"delete_confirm_{user_id}")],
            [InlineKeyboardButton("Отмена", callback_data="delete_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "⚠️ Вы уверены, что хотите удалить все свои данные?\n\n"
            "Это действие необратимо. Будут удалены:\n"
            "• Все записи эмоций\n"
            "• Настройки уведомлений\n"
            "• История и статистика",
            reply_markup=reply_markup
        )
    
    async def pause_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pause command"""
        if not await self._check_rate_limits(update, 'pause'):
            return
            
        user_id = update.effective_user.id
        logger.info(f"Received /pause from user {user_id}")
        
        try:
            self.db.update_user_paused(user_id, True)
            try:
                await self.scheduler.stop_user_schedule(user_id)
            except Exception as e:
                logger.error(f"Error stopping schedule for user {user_id}: {e}")
            
            await update.message.reply_text("Уведомления приостановлены. Используйте /resume для возобновления.")
        except Exception as e:
            logger.error(f"Error pausing user {user_id}: {e}")
            await update.message.reply_text("Произошла ошибка. Попробуйте позже.")
    
    async def resume_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resume command"""
        if not await self._check_rate_limits(update, 'resume'):
            return
            
        user_id = update.effective_user.id
        logger.info(f"Received /resume from user {user_id}")
        
        try:
            self.db.update_user_paused(user_id, False)
            try:
                await self.scheduler.start_user_schedule(user_id)
            except Exception as e:
                logger.error(f"Error starting schedule for user {user_id}: {e}")
            
            await update.message.reply_text("Уведомления возобновлены!")
        except Exception as e:
            logger.error(f"Error resuming user {user_id}: {e}")
            await update.message.reply_text("Произошла ошибка. Попробуйте позже.")
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command"""
        if not await self._check_rate_limits(update, 'stats'):
            return
            
        user_id = update.effective_user.id
        logger.info(f"Received /stats from user {user_id}")
        
        try:
            stats = self.db.get_global_stats()
            await update.message.reply_text(
                f"📊 Статистика EmoJournal:\n\n"
                f"👥 Всего пользователей: {stats['total_users']}\n"
                f"📝 Всего записей: {stats['total_entries']}\n"
                f"📅 Активных за неделю: {stats['active_weekly']}\n"
                f"📊 Подписано на саммари: {stats['weekly_summary_users']}"
            )
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            await update.message.reply_text("Не удалось получить статистику.")
    
    # Добавляем метод для отправки пингов из scheduler
    async def send_emotion_ping(self, user_id: int, chat_id: int) -> bool:
        """Send emotion ping to user - called by scheduler"""
        try:
            keyboard = [
                [InlineKeyboardButton("Ответить", callback_data=f"respond_{user_id}")],
                [InlineKeyboardButton("Отложить на 15 мин", callback_data=f"snooze_{user_id}")],
                [InlineKeyboardButton("Пропустить сегодня", callback_data=f"skip_{user_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            ping_text = """🌟 Как ты сейчас?

Если хочется — выбери 1-2 слова или просто опиши своими словами.

<i>Сам факт, что ты это заметишь и назовёшь, — уже шаг к ясности.</i>"""
            
            await self.bot.send_message(
                chat_id=chat_id,
                text=ping_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            
            logger.info(f"Sent emotion ping to user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send emotion ping to user {user_id}: {e}")
            return False
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard callbacks"""
        query = update.callback_query
        
        # Check rate limits for callbacks
        if not await self._check_rate_limits(update):
            return
            
        await query.answer()
        
        data = query.data
        user_id = query.from_user.id
        
        logger.info(f"Received callback {data} from user {user_id}")
        
        try:
            if data.startswith("respond_"):
                await self._start_emotion_flow(query, user_id)
            elif data.startswith("snooze_"):
                await self._snooze_ping(query, user_id)
            elif data.startswith("skip_"):
                await self._skip_today(query, user_id)
            elif data.startswith("emotion_"):
                await self._handle_emotion_selection(query, data)
            elif data.startswith("delete_confirm_"):
                await self._confirm_delete(query, user_id)
            elif data == "delete_cancel":
                await query.edit_message_text("Удаление отменено")
            elif data == "show_emotions":
                await self._show_emotion_categories(query)
            elif data.startswith("category_"):
                await self._show_category_emotions(query, data)
            elif data == "other_emotion":
                await self._request_custom_emotion(query)
            elif data == "skip_cause":
                await self._skip_cause_and_finish(query, user_id)
            
            # Summary period selection callbacks
            elif data.startswith("summary_period_"):
                await self._handle_summary_period_selection(query, data, user_id)
            elif data == "summary_period_custom":
                await self._request_custom_period(query, user_id)
            
            # Settings callbacks
            elif data == "toggle_weekly_summary":
                await self._toggle_weekly_summary(query, user_id)
            elif data == "change_summary_time":
                await self._change_summary_time(query, user_id)
            elif data == "settings_close":
                await query.edit_message_text("✅ Настройки сохранены!")
            
            # Time selection callbacks
            elif data.startswith("time_hour_"):
                await self._set_summary_time(query, data, user_id)
            elif data == "back_to_settings":
                await self._refresh_settings_display(query, user_id)
            elif data == "show_summary_periods":
                # Show period selection again
                keyboard = [
                    [
                        InlineKeyboardButton("7 дней", callback_data="summary_period_7"),
                        InlineKeyboardButton("2 недели", callback_data="summary_period_14")
                    ],
                    [
                        InlineKeyboardButton("30 дней", callback_data="summary_period_30"),
                        InlineKeyboardButton("3 месяца", callback_data="summary_period_90")
                    ],
                    [
                        InlineKeyboardButton("Другой период", callback_data="summary_period_custom")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    "📊 За какой период показать сводку?",
                    reply_markup=reply_markup
                )
            elif data == "export_csv_inline":
                # Handle inline CSV export
                try:
                    csv_data = await self.analyzer.export_csv(user_id)
                    if csv_data:
                        # Send as document
                        import io
                        
                        csv_file = io.BytesIO(csv_data.encode('utf-8'))
                        csv_file.name = f"emojournal_export_{datetime.now().strftime('%Y%m%d')}.csv"
                        
                        bot = query.bot
                        await bot.send_document(
                            chat_id=query.message.chat_id,
                            document=csv_file,
                            caption="Ваши данные в формате CSV"
                        )
                        await query.answer("CSV файл отправлен!")
                    else:
                        await query.answer("Пока нет данных для экспорта", show_alert=True)
                except Exception as e:
                    logger.error(f"Error exporting CSV inline for user {user_id}: {e}")
                    await query.answer("Ошибка при экспорте данных", show_alert=True)
                    
        except Exception as e:
            logger.error(f"Error handling callback {data} for user {user_id}: {e}")
            await query.edit_message_text("Произошла ошибка. Попробуйте позже.")
    
    async def _handle_summary_period_selection(self, query, data: str, user_id: int):
        """Handle summary period selection (7, 14, 30, 90 days)"""
        try:
            # Extract days from callback data
            period_str = data.replace("summary_period_", "")
            days = int(period_str)
            
            # Show "generating" message
            await query.edit_message_text(f"📊 Генерирую сводку за {days} дней...")
            
            # Generate summary
            summary = await self.analyzer.generate_summary(user_id, days)
            
            # Add period info to summary
            period_text = self._get_period_text(days)
            enhanced_summary = f"📊 <b>Сводка за {period_text}</b>\n\n{summary}"
            
            # Add action buttons after summary
            keyboard = [
                [InlineKeyboardButton("Другой период", callback_data="show_summary_periods")],
                [InlineKeyboardButton("📥 Экспорт CSV", callback_data="export_csv_inline")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                enhanced_summary,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error(f"Error generating summary for {days} days: {e}")
            await query.edit_message_text("Не удалось сформировать сводку. Попробуйте позже.")
    
    async def _request_custom_period(self, query, user_id: int):
        """Request custom period input"""
        self._set_user_state(user_id, 'waiting_for_custom_period')
        
        await query.edit_message_text(
            "📊 Введите количество дней для анализа (от 1 до 90):\n\n"
            "Например: 14 (для двух недель)"
        )
    
    async def _toggle_weekly_summary(self, query, user_id: int):
        """Toggle weekly summary setting"""
        try:
            # Get current settings
            settings = self.db.get_user_settings(user_id)
            current_enabled = settings.get('weekly_summary_enabled', True) if settings else True
            
            # Toggle setting
            new_enabled = not current_enabled
            self.db.update_user_settings(user_id, weekly_summary_enabled=new_enabled)
            
            # Update display
            await self._refresh_settings_display(query, user_id)
            
        except Exception as e:
            logger.error(f"Error toggling weekly summary for user {user_id}: {e}")
            await query.answer("Произошла ошибка при изменении настройки", show_alert=True)
    
    async def _change_summary_time(self, query, user_id: int):
        """Show time selection for summary delivery"""
        keyboard = []
        
        # Create time options (evening hours)
        time_options = [18, 19, 20, 21, 22, 23]
        for i in range(0, len(time_options), 2):
            row = []
            for j in range(2):
                if i + j < len(time_options):
                    hour = time_options[i + j]
                    row.append(InlineKeyboardButton(
                        f"{hour:02d}:00", 
                        callback_data=f"time_hour_{hour}"
                    ))
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("← Назад к настройкам", callback_data="back_to_settings")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🕘 Выберите время для получения еженедельных саммари:",
            reply_markup=reply_markup
        )
    
    async def _set_summary_time(self, query, data: str, user_id: int):
        """Set summary delivery time"""
        try:
            # Extract hour from callback data
            hour_str = data.replace("time_hour_", "")
            hour = int(hour_str)
            
            # Validate hour
            if not (0 <= hour <= 23):
                await query.answer("Неверное время", show_alert=True)
                return
            
            # Update setting
            self.db.update_user_settings(user_id, summary_time_hour=hour)
            
            # Back to settings
            await self._refresh_settings_display(query, user_id)
            
        except Exception as e:
            logger.error(f"Error setting summary time for user {user_id}: {e}")
            await query.answer("Произошла ошибка при изменении времени", show_alert=True)
    
    async def _refresh_settings_display(self, query, user_id: int):
        """Refresh settings display with current values"""
        try:
            settings = self.db.get_user_settings(user_id)
            weekly_enabled = settings.get('weekly_summary_enabled', True) if settings else True
            summary_hour = settings.get('summary_time_hour', 21) if settings else 21
            
            weekly_text = "✅ Включены" if weekly_enabled else "❌ Отключены"
            keyboard = [
                [InlineKeyboardButton(f"Еженедельные саммари: {weekly_text}", 
                                    callback_data="toggle_weekly_summary")],
                [InlineKeyboardButton(f"Время отправки: {summary_hour:02d}:00", 
                                    callback_data="change_summary_time")],
                [InlineKeyboardButton("💾 Сохранить и закрыть", 
                                    callback_data="settings_close")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "⚙️ <b>Настройки EmoJournal</b>\n\n"
                f"📅 <b>Автоматические саммари:</b> {weekly_text}\n"
                f"🕘 <b>Время отправки:</b> каждое воскресенье в {summary_hour:02d}:00\n\n"
                "Выберите что хотите изменить:",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error(f"Error refreshing settings for user {user_id}: {e}")
            await query.edit_message_text("Произошла ошибка при обновлении настроек.")
    
    def _get_period_text(self, days: int) -> str:
        """Get human-readable period text"""
        if days == 7:
            return "неделю"
        elif days == 14:
            return "2 недели"
        elif days == 30:
            return "месяц"
        elif days == 90:
            return "3 месяца"
        else:
            return f"{days} дней"
    
    async def _start_emotion_flow(self, query, user_id: int):
        """Start emotion recording flow"""
        self._clear_user_state(user_id)
        
        keyboard = [
            [InlineKeyboardButton("Показать идеи эмоций", callback_data="show_emotions")],
            [InlineKeyboardButton("Другое, напишу сам(а)", callback_data="other_emotion")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            self.texts.EMOTION_QUESTION,
            reply_markup=reply_markup
        )
    
    async def _show_emotion_categories(self, query):
        """Show emotion categories"""
        keyboard = []
        categories = [
            ("Радость/Удовлетворение", "category_joy"),
            ("Интерес/Любопытство", "category_interest"),
            ("Спокойствие/Умиротворение", "category_calm"),
            ("Тревога/Беспокойство", "category_anxiety"),
            ("Грусть/Печаль", "category_sadness"),
            ("Злость/Раздражение", "category_anger"),
            ("Стыд/Вина", "category_shame"),
            ("Усталость/Истощение", "category_fatigue"),
            ("Другое", "other_emotion")
        ]
        
        for name, callback in categories:
            keyboard.append([InlineKeyboardButton(name, callback_data=callback)])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Выбери группу эмоций, которая ближе всего:",
            reply_markup=reply_markup
        )
    
    async def _show_category_emotions(self, query, data: str):
        """Show specific emotions in category"""
        category = data.replace("category_", "")
        
        emotions_map = {
            "joy": ["радость", "счастье", "восторг", "удовлетворение", "благодарность", "вдохновение"],
            "interest": ["интерес", "любопытство", "увлечённость", "восхищение", "предвкушение"],
            "calm": ["спокойствие", "умиротворение", "расслабленность", "безмятежность", "принятие"],
            "anxiety": ["тревога", "беспокойство", "нервозность", "волнение", "напряжение", "страх"],
            "sadness": ["грусть", "печаль", "тоска", "уныние", "разочарование", "сожаление"],
            "anger": ["злость", "раздражение", "гнев", "возмущение", "обида", "фрустрация"],
            "shame": ["стыд", "вина", "смущение", "неловкость", "сожаление", "самокритика"],
            "fatigue": ["усталость", "истощение", "вялость", "апатия", "безразличие", "выгорание"]
        }
        
        emotions = emotions_map.get(category, [])
        keyboard = []
        
        for emotion in emotions:
            keyboard.append([InlineKeyboardButton(emotion.title(), callback_data=f"emotion_{emotion}")])
        
        keyboard.append([InlineKeyboardButton("← Назад к категориям", callback_data="show_emotions")])
        keyboard.append([InlineKeyboardButton("Другое, напишу сам(а)", callback_data="other_emotion")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Выбери конкретную эмоцию:",
            reply_markup=reply_markup
        )
    
    async def _handle_emotion_selection(self, query, data: str):
        """Handle specific emotion selection - asks for cause"""
        emotion = data.replace("emotion_", "")
        user_id = query.from_user.id
        
        # Validate emotion
        emotion_validated = sanitize_user_input(emotion, "emotion")
        if not emotion_validated:
            await query.edit_message_text("Некорректная эмоция. Попробуйте еще раз.")
            return
        
        # Store emotion in user state for the next step
        self._set_user_state(user_id, 'waiting_for_cause', {'emotion': emotion_validated})
        
        # Ask for cause/trigger
        keyboard = [
            [InlineKeyboardButton("Пропустить", callback_data="skip_cause")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"✨ Выбрана эмоция: {emotion_validated.title()}\n\n"
            f"{self.texts.CAUSE_QUESTION}",
            reply_markup=reply_markup
        )
    
    async def _request_custom_emotion(self, query):
        """Request custom emotion input"""
        user_id = query.from_user.id
        self._set_user_state(user_id, 'waiting_for_custom_emotion')
        
        await query.edit_message_text(
            "Опиши своими словами, как ты сейчас себя чувствуешь.\n\n"
            "Можно одним словом или фразой — как удобно."
        )
    
    async def _skip_cause_and_finish(self, query, user_id: int):
        """Skip cause entry and finish emotion recording"""
        user_state = self._get_user_state(user_id)
        emotion = user_state.get('emotion', 'неизвестно')
        
        # Save emotion without cause
        try:
            await self._save_emotion_entry(user_id, emotion, '')
            self._clear_user_state(user_id)
            
            await query.edit_message_text(
                f"✨ Спасибо!\n\n"
                f"Записана эмоция: {emotion.title()}\n\n"
                f"Уже сам факт, что ты это заметил(а) и назвал(а), — шаг к ясности.\n\n"
                f"💡 Чтобы записать ещё одну эмоцию, используй /note"
            )
        except Exception as e:
            logger.error(f"Error saving emotion entry: {e}")
            await query.edit_message_text("Произошла ошибка при сохранении. Попробуйте позже.")
    
    async def _snooze_ping(self, query, user_id: int):
        """Snooze notification for 15 minutes"""
        await query.edit_message_text("Напомню через 15 минут ⏰")
        try:
            await self.scheduler.schedule_snooze(user_id, 15)
        except Exception as e:
            logger.error(f"Error scheduling snooze for user {user_id}: {e}")
    
    async def _skip_today(self, query, user_id: int):
        """Skip today's remaining notifications"""
        await query.edit_message_text("Хорошо, сегодня больше не побеспокою")
        try:
            await self.scheduler.skip_today(user_id)
        except Exception as e:
            logger.error(f"Error skipping today for user {user_id}: {e}")
    
    async def _confirm_delete(self, query, user_id: int):
        """Confirm user data deletion"""
        try:
            self.db.delete_user_data(user_id)
            try:
                await self.scheduler.stop_user_schedule(user_id)
            except Exception as e:
                logger.error(f"Error stopping schedule during delete for user {user_id}: {e}")
            self._clear_user_state(user_id)
            
            await query.edit_message_text(
                "Все ваши данные удалены.\n\n"
                "Спасибо, что использовали EmoJournal!\n"
                "Если захотите начать заново — отправьте /start"
            )
        except Exception as e:
            logger.error(f"Error deleting user data: {e}")
            await query.edit_message_text("Произошла ошибка при удалении данных.")
    
    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages (emotion/cause/note input and custom period) with security validation"""
        if not await self._check_rate_limits(update):
            return
            
        user_id = update.effective_user.id
        raw_text = update.message.text
        
        logger.info(f"Received text message from user {user_id}: {raw_text[:50]}...")
        
        user_state = self._get_user_state(user_id)
        
        if user_state.get('state') == 'waiting_for_custom_emotion':
            # User entered custom emotion, validate and ask for cause
            emotion = sanitize_user_input(raw_text, "emotion")
            if not emotion:
                await update.message.reply_text(
                    "Некорректное название эмоции. Попробуйте использовать простые слова без специальных символов."
                )
                return
            
            self._set_user_state(user_id, 'waiting_for_cause', {'emotion': emotion})
            
            keyboard = [
                [InlineKeyboardButton("Пропустить", callback_data="skip_cause")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"✨ Записана эмоция: {emotion.title()}\n\n"
                f"{self.texts.CAUSE_QUESTION}",
                reply_markup=reply_markup
            )
            
        elif user_state.get('state') == 'waiting_for_cause':
            # User entered cause/trigger, validate and save complete entry
            cause = sanitize_user_input(raw_text, "cause")
            if not cause:
                await update.message.reply_text(
                    "Некорректное описание причины. Попробуйте написать проще."
                )
                return
            
            emotion = user_state.get('emotion', 'неизвестно')
            
            try:
                await self._save_emotion_entry(user_id, emotion, cause)
                self._clear_user_state(user_id)
                
                await update.message.reply_text(
                    f"✨ Спасибо!\n\n"
                    f"Эмоция: {emotion.title()}\n"
                    f"Триггер: {cause}\n\n"
                    f"Уже сам факт, что ты это заметил(а) и назвал(а), — шаг к ясности.\n\n"
                    f"💡 Чтобы записать ещё одну эмоцию, используй /note"
                )
            except Exception as e:
                logger.error(f"Failed to save entry for user {user_id}: {e}")
                await update.message.reply_text("Произошла ошибка при сохранении. Попробуйте позже.")
        
        elif user_state.get('state') == 'waiting_for_custom_period':
            # User entered custom period for summary
            try:
                days = int(raw_text.strip())
                if not (1 <= days <= 90):
                    await update.message.reply_text(
                        "Количество дней должно быть от 1 до 90. Попробуйте еще раз."
                    )
                    return
                
                self._clear_user_state(user_id)
                
                # Generate summary for custom period
                period_text = self._get_period_text(days)
                await update.message.reply_text(f"📊 Генерирую сводку за {period_text}...")
                
                summary = await self.analyzer.generate_summary(user_id, days)
                enhanced_summary = f"📊 <b>Сводка за {period_text}</b>\n\n{summary}"
                
                # Add action buttons
                keyboard = [
                    [InlineKeyboardButton("Другой период", callback_data="show_summary_periods")],
                    [InlineKeyboardButton("📥 Экспорт CSV", callback_data="export_csv_inline")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    enhanced_summary,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
                
            except ValueError:
                await update.message.reply_text(
                    "Пожалуйста, введите число от 1 до 90."
                )
            except Exception as e:
                logger.error(f"Error generating custom period summary: {e}")
                await update.message.reply_text("Не удалось сформировать сводку. Попробуйте позже.")
                
        else:
            # Regular text message - treat as emotion
            emotion = sanitize_user_input(raw_text, "emotion")
            if not emotion:
                await update.message.reply_text(
                    "Не удалось распознать эмоцию. Попробуйте использовать команду /note для структурированного ввода."
                )
                return
            
            self._set_user_state(user_id, 'waiting_for_cause', {'emotion': emotion})
            
            keyboard = [
                [InlineKeyboardButton("Пропустить", callback_data="skip_cause")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"✨ Записана эмоция: {emotion.title()}\n\n"
                f"{self.texts.CAUSE_QUESTION}",
                reply_markup=reply_markup
            )
    
    async def _save_emotion_entry(self, user_id: int, emotion_text: str, cause_text: str = ''):
        """Save emotion entry to database with validation"""
        try:
            # Ensure user exists (auto-create if needed)
            user = self.db.get_user(user_id)
            if not user:
                user = self.db.create_user(user_id, user_id)  # Use user_id as chat_id
                try:
                    await self.scheduler.start_user_schedule(user_id)
                except Exception as e:
                    logger.error(f"Error starting schedule for new user {user_id}: {e}")
                logger.info(f"Auto-created user {user_id}")
            
            # Additional validation
            emotion_validated = sanitize_user_input(emotion_text, "emotion")
            cause_validated = sanitize_user_input(cause_text, "cause") if cause_text else ""
            
            if not emotion_validated:
                raise ValueError("Invalid emotion text")
            
            entry_data = {
                'emotions': [emotion_validated.lower()],
                'cause': cause_validated,
                'note': f"{emotion_validated}" + (f" (причина: {cause_validated})" if cause_validated else ""),
                'valence': None,
                'arousal': None
            }
            
            self.db.create_entry(
                user_id=user_id,
                emotions=json.dumps(entry_data['emotions'], ensure_ascii=False),
                cause=entry_data['cause'],
                note=entry_data['note'],
                valence=entry_data['valence'],
                arousal=entry_data['arousal']
            )
            
            logger.info(f"Saved emotion entry for user {user_id}: {emotion_validated}")
            
        except Exception as e:
            logger.error(f"Failed to save emotion entry for user {user_id}: {e}")
            raise
    
    def create_application(self):
        """Create and configure telegram application"""
        application = Application.builder().token(self.bot_token).build()
        
        # Command handlers
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("note", self.note_command))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("timezone", self.timezone_command))
        application.add_handler(CommandHandler("summary", self.summary_command))
        application.add_handler(CommandHandler("settings", self.settings_command))
        application.add_handler(CommandHandler("export", self.export_command))
        application.add_handler(CommandHandler("delete_me", self.delete_me_command))
        application.add_handler(CommandHandler("pause", self.pause_command))
        application.add_handler(CommandHandler("resume", self.resume_command))
        application.add_handler(CommandHandler("stats", self.stats_command))
        
        # Callback and message handlers
        application.add_handler(CallbackQueryHandler(self.handle_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))
        
        logger.info("Created telegram application with all handlers")
        return application
    
    async def run_webhook(self):
        """Run bot in webhook mode for Render - ENHANCED VERSION WITH DETAILED DIAGNOSTICS"""
        logger.info("Starting bot in webhook mode...")
        
        application = self.create_application()
        
        # Запускаем scheduler ПОСЛЕ создания application
        try:
            await self.scheduler.start()
            logger.info("Scheduler started successfully")
        except Exception as e:
            logger.error(f"Error starting scheduler: {e}")
        
        # Initialize application
        await application.initialize()
        await application.start()
        
        # ИСПРАВЛЕНИЕ: Принудительно удаляем старый webhook
        try:
            delete_result = await application.bot.delete_webhook()
            logger.info(f"Deleted old webhook: {delete_result}")
            await asyncio.sleep(2)  # Пауза для применения изменений
        except Exception as e:
            logger.warning(f"Could not delete old webhook: {e}")
        
        # Set new webhook
        webhook_url = self.webhook_url
        if not webhook_url.endswith('/webhook'):
            webhook_url += '/webhook'
        
        logger.info(f"Setting webhook to: {webhook_url}")
        
        # ИСПРАВЛЕНИЕ: Улучшенная установка webhook
        try:
            webhook_result = await application.bot.set_webhook(
                url=webhook_url,
                allowed_updates=['message', 'callback_query'],
                drop_pending_updates=True,  # Очищаем накопившиеся обновления
                max_connections=5
            )
            logger.info(f"Webhook set successfully: {webhook_result}")
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}")
            raise
        
        # ДОБАВЛЯЕМ: Проверка статуса webhook после установки
        try:
            await asyncio.sleep(1)  # Пауза
            webhook_info = await application.bot.get_webhook_info()
            logger.info(f"Webhook info after setup:")
            logger.info(f"  URL: {webhook_info.url}")
            logger.info(f"  Pending updates: {webhook_info.pending_update_count}")
            logger.info(f"  Max connections: {webhook_info.max_connections}")
            if webhook_info.last_error_date:
                logger.warning(f"  Last error: {webhook_info.last_error_message} at {webhook_info.last_error_date}")
            else:
                logger.info("  No webhook errors detected")
        except Exception as e:
            logger.warning(f"Could not get webhook info: {e}")
        
        # Create aiohttp web server
        from aiohttp import web
        from aiohttp.web_request import Request
        
        async def webhook_handler(request: Request):
            """Handle incoming webhook requests - MAXIMUM ENHANCED LOGGING"""
            logger.info("!!! WEBHOOK HANDLER CALLED !!!")
            
            try:
                # Логируем КАЖДЫЙ входящий запрос
                client_ip = request.remote or 'unknown'
                headers = dict(request.headers)
                logger.info(f"=== WEBHOOK REQUEST FROM {client_ip} ===")
                logger.info(f"Request method: {request.method}")
                logger.info(f"Request URL: {request.url}")
                logger.info(f"Request headers: {headers}")
                
                # Получаем тело запроса
                body = await request.text()
                logger.info(f"Webhook body length: {len(body)} chars")
                logger.info(f"Webhook body preview: {body[:300]}...")
                
                if not body:
                    logger.warning("Empty webhook body received")
                    return web.Response(status=200, text="Empty body")
                
                # Парсим JSON
                try:
                    update_data = json.loads(body)
                    logger.info(f"Parsed JSON successfully. Keys: {list(update_data.keys())}")
                    logger.info(f"Update data: {update_data}")
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON: {e}")
                    logger.error(f"Raw body: {body}")
                    return web.Response(status=400, text="Invalid JSON")
                
                # Создаем Update объект
                try:
                    update = Update.de_json(update_data, application.bot)
                    logger.info(f"Created Update object: ID={update.update_id}")
                    
                    # Детальная информация об обновлении
                    if update.message:
                        msg = update.message
                        logger.info(f"Message from user {msg.from_user.id} (@{msg.from_user.username}): '{msg.text}'")
                        logger.info(f"Chat ID: {msg.chat.id}, Message ID: {msg.message_id}")
                    elif update.callback_query:
                        cb = update.callback_query
                        logger.info(f"Callback from user {cb.from_user.id}: '{cb.data}'")
                    else:
                        logger.info(f"Other update type: {type(update)}")
                        logger.info(f"Update content: {update}")
                        
                except Exception as e:
                    logger.error(f"Failed to create Update object: {e}")
                    logger.error(f"Update data was: {update_data}")
                    return web.Response(status=500, text="Update creation failed")
                
                # Обрабатываем обновление
                try:
                    logger.info(f"Processing update {update.update_id}...")
                    await application.process_update(update)
                    logger.info(f"Successfully processed update {update.update_id}")
                except Exception as e:
                    logger.error(f"Error processing update {update.update_id}: {e}")
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    # Не возвращаем ошибку, чтобы Telegram не повторял запрос
                
                logger.info(f"=== WEBHOOK REQUEST COMPLETED ===")
                return web.Response(status=200, text="OK")
                
            except Exception as e:
                logger.error(f"Unexpected webhook error: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                return web.Response(status=500, text=f"Error: {e}")
        
        async def health_handler(request: Request):
            """Health check endpoint - ENHANCED"""
            try:
                # Проверяем что бот жив
                bot_info = await application.bot.get_me()
                logger.info(f"Health check: Bot @{bot_info.username} is alive")
                
                return web.Response(
                    text=f"OK - Bot @{bot_info.username} is running", 
                    status=200
                )
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                return web.Response(text=f"Health check failed: {e}", status=500)
        
        async def root_handler(request: Request):
            """Root page handler - ENHANCED"""
            try:
                bot_info = await application.bot.get_me()
                status_info = {
                    "status": "running",
                    "bot_username": bot_info.username,
                    "bot_id": bot_info.id,
                    "webhook_url": webhook_url
                }
                return web.Response(
                    text=f"EmoJournal Bot is running\n{status_info}", 
                    status=200
                )
            except Exception as e:
                return web.Response(
                    text=f"EmoJournal Bot - Status unknown: {e}", 
                    status=200
                )
        
        # Create web application
        app = web.Application()
        app.router.add_post('/webhook', webhook_handler)
        app.router.add_get('/health', health_handler)
        app.router.add_get('/', root_handler)
        
        # Start web server
        runner = web.AppRunner(app)
        await runner.setup()
        
        site = web.TCPSite(runner, '0.0.0.0', self.port)
        await site.start()
        
        logger.info(f"Bot started in webhook mode on port {self.port}")
        logger.info(f"Webhook URL: {webhook_url}")
        logger.info("=== SERVER IS READY TO RECEIVE WEBHOOKS ===")
        
        return application, runner


async def main():
    """Main function"""
    logger.info("Starting EmoJournal Bot...")
    
    bot = EmoJournalBot()
    
    try:
        application, runner = await bot.run_webhook()
        
        # Keep running indefinitely
        await asyncio.Event().wait()
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise
