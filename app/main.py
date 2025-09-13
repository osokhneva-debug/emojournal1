#!/usr/bin/env python3
"""
EmoJournal Telegram Bot - Main Application
Emotion tracking bot with random scheduling and weekly analytics
"""

import logging
import os
import asyncio
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from telegram.error import TelegramError

from .db import Database, User, Entry
from .scheduler import RandomScheduler
from .i18n import Texts
from .analysis import WeeklyAnalyzer

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
        
        # User states for multi-step conversations (simplified in-memory storage)
        self.user_states: Dict[int, Dict[str, Any]] = {}
        
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
    
    def _set_user_state(self, user_id: int, state: str, data: Dict[str, Any] = None):
        """Set user conversation state"""
        if user_id not in self.user_states:
            self.user_states[user_id] = {}
        self.user_states[user_id]['state'] = state
        if data:
            self.user_states[user_id].update(data)
    
    def _get_user_state(self, user_id: int) -> Dict[str, Any]:
        """Get user conversation state"""
        return self.user_states.get(user_id, {})
    
    def _clear_user_state(self, user_id: int):
        """Clear user conversation state"""
        if user_id in self.user_states:
            del self.user_states[user_id]
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command with onboarding"""
        if not self._check_rate_limit(update.effective_user.id):
            return
            
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        # Clear any existing state
        self._clear_user_state(user_id)
        
        # Create or get user
        user = self.db.get_user(user_id)
        if not user:
            user = self.db.create_user(user_id, chat_id)
            # Start daily scheduling for new user
            await self.scheduler.start_user_schedule(user_id)
        
        # Set bot commands menu
        commands = [
            BotCommand("start", "🎭 Запустить бота"),
            BotCommand("note", "📝 Записать эмоцию сейчас"),
            BotCommand("help", "❓ Помощь и информация"),
            BotCommand("summary", "📊 Сводка за неделю"),
            BotCommand("export", "📥 Экспорт данных в CSV"),
            BotCommand("timezone", "🌍 Настройка часового пояса"),
            BotCommand("pause", "⏸️ Приостановить уведомления"),
            BotCommand("resume", "▶️ Возобновить уведомления"),
            BotCommand("stats", "📈 Статистика бота"),
            BotCommand("delete_me", "🗑️ Удалить все данные")
        ]
        
        await context.bot.set_my_commands(commands)
        
        await update.message.reply_text(
            self.texts.ONBOARDING,
            parse_mode='HTML'
        )
    
    async def note_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /note command for manual emotion entry"""
        if not self._check_rate_limit(update.effective_user.id):
            return
        
        user_id = update.effective_user.id
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
        elif data == "skip_cause":
            await self._skip_cause_and_finish(query, user_id)
    
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
        """Handle specific emotion selection - now asks for cause"""
        emotion = data.replace("emotion_", "")
        user_id = query.from_user.id
        
        # Store emotion in user state for the next step
        self._set_user_state(user_id, 'waiting_for_cause', {'emotion': emotion})
        
        # Ask for cause/trigger
        keyboard = [
            [InlineKeyboardButton("Пропустить", callback_data="skip_cause")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"✨ Выбрана эмоция: {emotion.title()}\n\n"
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
        await self._save_emotion_entry(user_id, emotion, '')
        self._clear_user_state(user_id)
        
        await query.edit_message_text(
            f"✨ Спасибо!\n\n"
            f"Записана эмоция: {emotion.title()}\n\n"
            f"Уже сам факт, что ты это заметил(а) и назвал(а), — шаг к ясности.\n\n"
            f"💡 Чтобы записать ещё одну эмоцию, используй /note"
        )
    
    async def _snooze_ping(self, query, user_id: int):
        """Snooze notification for 15 minutes"""
        await query.edit_message_text("Напомню через 15 минут ⏰")
        await self.scheduler.schedule_snooze(user_id, 15)
    
    async def _skip_today(self, query, user_id: int):
        """Skip today's remaining notifications"""
        await query.edit_message_text("Хорошо, сегодня больше не побеспокою")
        await self.scheduler.skip_today(user_id)
    
    async def _confirm_delete(self, query, user_id: int):
        """Confirm user data deletion"""
        self.db.delete_user_data(user_id)
        await self.scheduler.stop_user_schedule(user_id)
        self._clear_user_state(user_id)
        
        await query.edit_message_text(
            "Все ваши данные удалены.\n\n"
            "Спасибо, что использовали EmoJournal!\n"
            "Если захотите начать заново — отправьте /start"
        )
    
    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages (emotion/cause/note input)"""
        user_id = update.effective_user.id
        text = update.message.text.strip()
        user_state = self._get_user_state(user_id)
        
        if user_state.get('state') == 'waiting_for_custom_emotion':
            # User entered custom emotion, now ask for cause
            self._set_user_state(user_id, 'waiting_for_cause', {'emotion': text})
            
            keyboard = [
                [InlineKeyboardButton("Пропустить", callback_data="skip_cause")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"✨ Записана эмоция: {text.title()}\n\n"
                f"{self.texts.CAUSE_QUESTION}",
                reply_markup=reply_markup
            )
            
        elif user_state.get('state') == 'waiting_for_cause':
            # User entered cause/trigger, save complete entry
            emotion = user_state.get('emotion', text)
            cause = text
            
            await self._save_emotion_entry(user_id, emotion, cause)
            self._clear_user_state(user_id)
            
            await update.message.reply_text(
                f"✨ Спасибо!\n\n"
                f"Эмоция: {emotion.title()}\n"
                f"Триггер: {cause}\n\n"
                f"Уже сам факт, что ты это заметил(а) и назвал(а), — шаг к ясности.\n\n"
                f"💡 Чтобы записать ещё одну эмоцию, используй /note"
            )
            
        else:
            # Regular text message - treat as emotion
            self._set_user_state(user_id, 'waiting_for_cause', {'emotion': text})
            
            keyboard = [
                [InlineKeyboardButton("Пропустить", callback_data="skip_cause")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"✨ Записана эмоция: {text.title()}\n\n"
                f"{self.texts.CAUSE_QUESTION}",
                reply_markup=reply_markup
            )
    
    async def _save_emotion_entry(self, user_id: int, emotion_text: str, cause_text: str = ''):
        """Save emotion entry to database"""
        try:
            # Ensure user exists (auto-create if needed)
            user = self.db.get_user(user_id)
            if not user:
                user = self.db.create_user(user_id, user_id)  # Use user_id as chat_id
                await self.scheduler.start_user_schedule(user_id)
                logger.info(f"Auto-created user {user_id}")
            
            entry_data = {
                'emotions': [emotion_text.lower()],
                'cause': cause_text,
                'note': f"{emotion_text}" + (f" (причина: {cause_text})" if cause_text else ""),
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
    
    def create_application(self):
        """Create and configure telegram application"""
        application = Application.builder().token(self.bot_token).build()
        
        # Command handlers
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("note", self.note_command))
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
        
        # Initialize application
        await application.initialize()
        await application.start()
        
        # Set webhook
        webhook_url = self.webhook_url
        if not webhook_url.endswith('/webhook'):
            webhook_url += '/webhook'
        
        await application.bot.set_webhook(
            url=webhook_url,
            allowed_updates=['message', 'callback_query']
        )
        
        # Create aiohttp web server
        from aiohttp import web
        from aiohttp.web_request import Request
        
        async def webhook_handler(request: Request):
            """Handle incoming webhook requests"""
            try:
                body = await request.text()
                update_data = json.loads(body)
                update = Update.de_json(update_data, application.bot)
                
                # Process update
                await application.process_update(update)
                
                return web.Response(status=200)
                
            except Exception as e:
                logger.error(f"Webhook error: {e}")
                return web.Response(status=500)
        
        async def health_handler(request: Request):
            """Health check endpoint"""
            return web.Response(text="OK", status=200)
        
        async def root_handler(request: Request):
            """Root page handler"""
            return web.Response(text="EmoJournal Bot is running", status=200)
        
        # Create web application
        app = web.Application()
        app.router.add_post('/webhook', webhook_handler)
        app.router.add_get('/health', health_handler)
        app.router.add_get('/', root_handler)
        
        # Start web server
        from aiohttp import web
        runner = web.AppRunner(app)
        await runner.setup()
        
        site = web.TCPSite(runner, '0.0.0.0', self.port)
        await site.start()
        
        logger.info(f"Bot started in webhook mode on port {self.port}")
        logger.info(f"Webhook URL: {webhook_url}")
        
        return application, runner


async def main():
    """Main function"""
    bot = EmoJournalBot()
    
    try:
        application, runner = await bot.run_webhook()
        
        # Keep running indefinitely
        await asyncio.Event().wait()
        
    except Exception as e:  # ИСПРАВЛЕНО: добавлено 'as'
        logger.error(f"Failed to start bot: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
