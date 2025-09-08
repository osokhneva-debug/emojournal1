#!/usr/bin/env python3
"""
EmoJournal Telegram Bot - Main Application
Emotion tracking bot with random scheduling and weekly analytics
"""

import logging
import os
import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from telegram.error import TelegramError

from db import Database, User, Entry
from scheduler import RandomScheduler
from i18n import Texts
from analysis import WeeklyAnalyzer

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class EmoJournalBot:
    def __init__(self):
        self.db = Database()
        self.scheduler = RandomScheduler(self.db)
        self.texts = Texts()
        self.analyzer = WeeklyAnalyzer(self.db)
        
        # Environment validation
        self.bot_token = self._get_env_var('TELEGRAM_BOT_TOKEN')
        self.webhook_url = self._get_env_var('WEBHOOK_URL')
        self.port = int(os.getenv('PORT', '10000'))
        
        # Rate limiting storage (simple in-memory)
        self.rate_limits: Dict[int, datetime] = {}
        
    def _get_env_var(self, name: str) -> str:
        value = os.getenv(name)
        if not value:
            logger.error(f"Required environment variable {name} not set")
            raise ValueError(f"Environment variable {name} is required")
        return value
    
    def _check_rate_limit(self, user_id: int) -> bool:
        """Simple rate limiting: 1 command per 2 seconds"""
        now = datetime.now(timezone.utc)
        if user_id in self.rate_limits:
            if (now - self.rate_limits[user_id]).total_seconds() < 2:
                return False
        self.rate_limits[user_id] = now
        return True
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command with onboarding"""
        if not self._check_rate_limit(update.effective_user.id):
            return
            
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        # Create or get user
        user = self.db.get_user(user_id)
        if not user:
            user = self.db.create_user(user_id, chat_id)
            # Start daily scheduling for new user
            await self.scheduler.start_user_schedule(user_id)
        
        await update.message.reply_text(
            self.texts.ONBOARDING,
            parse_mode='HTML'
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        if not self._check_rate_limit(update.effective_user.id):
            return
            
        await update.message.reply_text(
            self.texts.HELP,
            parse_mode='HTML'
        )
    
    async def timezone_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /timezone command"""
        if not self._check_rate_limit(update.effective_user.id):
            return
            
        user_id = update.effective_user.id
        
        if context.args:
            tz_name = ' '.join(context.args)
            try:
                import zoneinfo
                zoneinfo.ZoneInfo(tz_name)  # Validate timezone
                self.db.update_user_timezone(user_id, tz_name)
                await update.message.reply_text(
                    f"Часовой пояс установлен: {tz_name}"
                )
                # Reschedule with new timezone
                await self.scheduler.start_user_schedule(user_id)
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
        """Handle /summary command"""
        if not self._check_rate_limit(update.effective_user.id):
            return
            
        user_id = update.effective_user.id
        days = 7
        
        if context.args:
            try:
                days = int(context.args[0])
                days = max(1, min(days, 90))  # Limit to 1-90 days
            except ValueError:
                pass
        
        summary = await self.analyzer.generate_summary(user_id, days)
        await update.message.reply_text(summary, parse_mode='HTML')
    
    async def export_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /export command"""
        if not self._check_rate_limit(update.effective_user.id):
            return
            
        user_id = update.effective_user.id
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
    
    async def delete_me_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /delete_me command"""
        if not self._check_rate_limit(update.effective_user.id):
            return
            
        user_id = update.effective_user.id
        
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
        if not self._check_rate_limit(update.effective_user.id):
            return
            
        user_id = update.effective_user.id
        self.db.update_user_paused(user_id, True)
        await self.scheduler.stop_user_schedule(user_id)
        
        await update.message.reply_text("Уведомления приостановлены. Используйте /resume для возобновления.")
    
    async def resume_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resume command"""
        if not self._check_rate_limit(update.effective_user.id):
            return
            
        user_id = update.effective_user.id
        self.db.update_user_paused(user_id, False)
        await self.scheduler.start_user_schedule(user_id)
        
        await update.message.reply_text("Уведомления возобновлены!")
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command"""
        if not self._check_rate_limit(update.effective_user.id):
            return
            
        stats = self.db.get_global_stats()
        await update.message.reply_text(
            f"📊 Статистика EmoJournal:\n\n"
            f"👥 Всего пользователей: {stats['total_users']}\n"
            f"📝 Всего записей: {stats['total_entries']}\n"
            f"📅 Активных за неделю: {stats['active_weekly']}"
        )
    
    async def emotion_ping(self, user_id: int):
        """Send emotion check-in to user"""
        try:
            user = self.db.get_user(user_id)
            if not user or user.paused:
                return
            
            keyboard = [
                [InlineKeyboardButton("Ответить", callback_data=f"respond_{user_id}")],
                [InlineKeyboardButton("Отложить на 15 мин", callback_data=f"snooze_{user_id}")],
                [InlineKeyboardButton("Пропустить сегодня", callback_data=f"skip_{user_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            from telegram import Bot
            bot = Bot(token=self.bot_token)
            await bot.send_message(
                chat_id=user.chat_id,
                text=self.texts.EMOTION_PING,
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Failed to send ping to user {user_id}: {e}")
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard callbacks"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user_id = query.from_user.id
        
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
    
    async def _start_emotion_flow(self, query, user_id: int):
        """Start emotion recording flow"""
        keyboard = [
            [InlineKeyboardButton("Показать идеи эмоций", callback_data="show_emotions")],
            [InlineKeyboardButton("Другое, напишу сам(а)", callback_data="other_emotion")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            self.texts.EMOTION_QUESTION,
            reply_markup=reply_markup
        )
        
        # Set user state for text input
        context = {"user_id": user_id, "step": "emotion_input"}
        # Store in database or memory (simplified)
    
    async def _show_emotion_categories(self, query):
        """Show emotion categories based on Plutchik's wheel and NVC"""
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
        """Handle specific emotion selection"""
        emotion = data.replace("emotion_", "")
        user_id = query.from_user.id
        
        # Store selected emotion and ask for intensity
        await query.edit_message_text(
            f"Выбрана эмоция: {emotion.title()}\n\n"
            "Насколько интенсивно это ощущается по шкале от 0 до 10?\n"
            "(0 — едва заметно, 10 — очень сильно)\n\n"
            "Просто напиши цифру или пропусти, отправив любой текст."
        )
    
    async def _request_custom_emotion(self, query):
        """Request custom emotion input"""
        await query.edit_message_text(
            "Опиши своими словами, как ты сейчас себя чувствуешь.\n\n"
            "Можно одним словом или фразой — как удобно."
        )
    
    async def _snooze_ping(self, query, user_id: int):
        """Snooze notification for 15 minutes"""
        await query.edit_message_text("Напомню через 15 минут ⏰")
        # Schedule reminder in 15 minutes
        await self.scheduler.schedule_snooze(user_id, 15)
    
    async def _skip_today(self, query, user_id: int):
        """Skip today's remaining notifications"""
        await query.edit_message_text("Хорошо, сегодня больше не побеспокою")
        await self.scheduler.skip_today(user_id)
    
    async def _confirm_delete(self, query, user_id: int):
        """Confirm user data deletion"""
        self.db.delete_user_data(user_id)
        await self.scheduler.stop_user_schedule(user_id)
        
        await query.edit_message_text(
            "Все ваши данные удалены.\n\n"
            "Спасибо, что использовали EmoJournal! 💙\n"
            "Если захотите начать заново — отправьте /start"
        )
    
    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages (emotion/cause/note input)"""
        user_id = update.effective_user.id
        text = update.message.text.strip()
        
        # Simple state management - in production use proper state storage
        # For now, just save as emotion entry
        await self._save_emotion_entry(user_id, text)
        
        await update.message.reply_text(
            self.texts.THANK_YOU,
            parse_mode='HTML'
        )
    
    async def _save_emotion_entry(self, user_id: int, emotion_text: str):
        """Save emotion entry to database"""
        try:
            # Simple parsing - in production use NLP for better extraction
            import json
            
            entry_data = {
                'emotions': [emotion_text.lower()],
                'cause': '',
                'note': emotion_text,
                'valence': None,
                'arousal': None
            }
            
            self.db.create_entry(
                user_id=user_id,
                emotions=json.dumps(entry_data['emotions']),
                cause=entry_data['cause'],
                note=entry_data['note'],
                valence=entry_data['valence'],
                arousal=entry_data['arousal']
            )
            
        except Exception as e:
            logger.error(f"Failed to save emotion entry: {e}")
    
    async def health_check(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Health check endpoint for Render"""
        return "OK"
    
    def create_application(self):
        """Create and configure telegram application"""
        application = Application.builder().token(self.bot_token).build()
        
        # Command handlers
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("timezone", self.timezone_command))
        application.add_handler(CommandHandler("summary", self.summary_command))
        application.add_handler(CommandHandler("export", self.export_command))
        application.add_handler(CommandHandler("delete_me", self.delete_me_command))
        application.add_handler(CommandHandler("pause", self.pause_command))
        application.add_handler(CommandHandler("resume", self.resume_command))
        application.add_handler(CommandHandler("stats", self.stats_command))
        
        # Callback and message handlers
        application.add_handler(CallbackQueryHandler(self.handle_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))
        
        return application
    
    async def run_webhook(self):
        """Run bot in webhook mode for Render"""
        application = self.create_application()
        
        # Start scheduler
        await self.scheduler.start()
        
        # Configure webhook
        await application.initialize()
        await application.start()
        
        # Set webhook
        webhook_path = "/webhook"
        await application.bot.set_webhook(
            url=f"{self.webhook_url}{webhook_path}",
            allowed_updates=['message', 'callback_query']
        )
        
        # Start webhook server
        from telegram.ext import Application
        webserver = application.updater.start_webhook(
            listen="0.0.0.0",
            port=self.port,
            url_path="webhook",
            webhook_url=f"{self.webhook_url}/webhook"
        )
        
        # Add health check endpoint
        from aiohttp import web
        app = web.Application()
        app.router.add_get('/health', lambda r: web.Response(text="OK"))
        
        logger.info(f"Bot started in webhook mode on port {self.port}")
        
        return application, webserver

async def main():
    """Main function"""
    bot = EmoJournalBot()
    
    try:
        application, webserver = await bot.run_webhook()
        
        # Keep running
        import signal
        import asyncio
        
        def signal_handler(sig, frame):
            logger.info("Shutting down...")
            webserver.stop()
            asyncio.create_task(application.stop())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Wait indefinitely
        await asyncio.Event().wait()
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())