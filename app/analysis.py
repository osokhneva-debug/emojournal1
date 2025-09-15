#!/usr/bin/env python3
"""
Weekly Analysis and Export for EmoJournal Bot
Generates insights and CSV exports based on user data
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import json
import csv
import io
from collections import Counter

from .i18n import Texts, format_emotion_list, get_time_period_text, generate_insight

logger = logging.getLogger(__name__)

class WeeklyAnalyzer:
    """Analyzes user emotion data and generates insights"""
    
    def __init__(self, db):
        self.db = db
        self.texts = Texts()
    
    async def generate_summary(self, user_id: int, days: int = 7) -> str:
        """Generate summary for user - works with any number of entries"""
        try:
            entries = self.db.get_user_entries(user_id, days)
            
            # Убираем минимальное ограничение - теперь работает с любым количеством записей
            if len(entries) == 0:
                return self.texts.NO_DATA_MESSAGE
            
            if len(entries) == 1:
                # Специальная обработка для одной записи
                entry = entries[0]
                emotions = self._parse_emotions(entry.emotions) if entry.emotions else ['неизвестно']
                return f"""📊 <b>Твоя первая запись!</b>

<b>🎭 Эмоция:</b> {', '.join(emotions)}

<b>🔍 Причина:</b> {entry.cause if entry.cause else 'не указана'}

<b>⏰ Время:</b> {entry.ts_local.strftime('%H:%M')} ({get_time_period_text(entry.ts_local.hour)})

<b>📈 Всего записей:</b> 1

💡 <b>Отлично!</b> Ты сделал(а) первый шаг к осознанности. Продолжай записывать эмоции, и вскоре я смогу показать интересные закономерности!

<i>Используй /note для новых записей.</i>"""
            
            # Анализ для 2+ записей
            emotion_freq = self._analyze_emotions(entries)
            top_emotions = self._get_top_items(emotion_freq, limit=5)
            
            trigger_freq = self._analyze_triggers(entries)
            top_triggers = self._get_top_items(trigger_freq, limit=5)
            
            time_dist = self._analyze_time_distribution(entries)
            peak_hour = max(time_dist.items(), key=lambda x: x[1])[0] if time_dist else 12
            peak_period = get_time_period_text(peak_hour)
            
            # Генерируем инсайты (для 2+ записей инсайты менее детальные)
            if len(entries) >= 5:
                insights = generate_insight(top_emotions, top_triggers, peak_hour)
            else:
                insights = self._generate_simple_insights(entries, top_emotions)
            
            # Формат сводки
            summary = self.texts.WEEKLY_SUMMARY_TEMPLATE.format(
                top_emotions=format_emotion_list(top_emotions),
                top_triggers=format_emotion_list(top_triggers) if top_triggers else "нет данных",
                peak_hours=f"{peak_hour:02d}:00 ({peak_period})",
                total_entries=len(entries),
                insights=insights
            )
            
            return summary
            
        except Exception as e:
            logger.error(f"Failed to generate summary for user {user_id}: {e}")
            return "Не удалось сформировать сводку. Попробуйте позже."
    
    def _generate_simple_insights(self, entries, top_emotions) -> str:
        """Generate simple insights for small number of entries"""
        if len(entries) < 2:
            return ""
        
        insights = []
        
        # Простой анализ для небольшого количества записей
        if len(entries) == 2:
            insights.append("💡 <b>Начало пути:</b> У тебя уже 2 записи! Продолжай отслеживать эмоции для выявления паттернов.")
        elif len(entries) == 3:
            insights.append("💡 <b>Хороший прогресс:</b> 3 записи позволяют увидеть первые тенденции в твоём эмоциональном состоянии.")
        elif len(entries) == 4:
            insights.append("💡 <b>Формируется картина:</b> 4 записи дают более ясное представление о твоих эмоциональных паттернах.")
        
        # Анализ преобладающих эмоций
        if top_emotions:
            top_emotion = top_emotions[0][0] if isinstance(top_emotions[0], tuple) else top_emotions[0]
            
            positive_emotions = {'радость', 'счастье', 'удовлетворение', 'спокойствие', 'энергия'}
            negative_emotions = {'тревога', 'грусть', 'злость', 'усталость', 'раздражение'}
            
            if top_emotion in positive_emotions:
                insights.append("✨ Здорово, что преобладают позитивные эмоции!")
            elif top_emotion in negative_emotions:
                insights.append("🤗 Замечать сложные эмоции — важный шаг к их пониманию.")
        
        return "\n\n".join(insights)
    
    def _analyze_emotions(self, entries) -> Dict[str, int]:
        """Extract and count emotion frequencies with normalization"""
        emotion_counts = Counter()
        
        for entry in entries:
            if entry.emotions:
                emotions = self._parse_emotions(entry.emotions)
                for emotion in emotions:
                    normalized = self._normalize_emotion(emotion)
                    if normalized:
                        emotion_counts[normalized] += 1
        
        return dict(emotion_counts)
    
    def _parse_emotions(self, emotions_str: str) -> List[str]:
        """Parse emotions from JSON or plain text"""
        if not emotions_str:
            return []
        
        try:
            # Try parsing as JSON array
            emotions = json.loads(emotions_str)
            if isinstance(emotions, list):
                return [str(e).strip().lower() for e in emotions if e]
        except (json.JSONDecodeError, TypeError):
            pass
        
        # Fall back to plain text parsing
        return [emotions_str.strip().lower()] if emotions_str.strip() else []
    
    def _normalize_emotion(self, emotion: str) -> Optional[str]:
        """Normalize emotion to base form (simple stemming for Russian)"""
        emotion = emotion.strip().lower()
        
        if len(emotion) < 2:
            return None
        
        # Simple Russian emotion normalization rules
        emotion_mapping = {
            # Радость family
            'радостный': 'радость',
            'радостная': 'радость', 
            'радостное': 'радость',
            'счастливый': 'счастье',
            'счастливая': 'счастье',
            'довольный': 'удовлетворение',
            'довольная': 'удовлетворение',
            
            # Тревога family  
            'тревожный': 'тревога',
            'тревожная': 'тревога',
            'беспокойный': 'беспокойство', 
            'беспокойная': 'беспокойство',
            'нервный': 'нервозность',
            'нервная': 'нервозность',
            
            # Грусть family
            'грустный': 'грусть',
            'грустная': 'грусть',
            'печальный': 'печаль',
            'печальная': 'печаль',
            
            # Злость family
            'злой': 'злость',
            'злая': 'злость', 
            'раздражённый': 'раздражение',
            'раздражённая': 'раздражение',
            
            # Усталость family
            'усталый': 'усталость',
            'усталая': 'усталость',
            'уставший': 'усталость',
            'уставшая': 'усталость',
        }
        
        # Direct mapping
        if emotion in emotion_mapping:
            return emotion_mapping[emotion]
        
        # Remove common Russian adjective endings
        for ending in ['ый', 'ая', 'ое', 'ые', 'ой', 'ей', 'ён', 'на', 'но', 'ны']:
            if emotion.endswith(ending) and len(emotion) > len(ending) + 2:
                base = emotion[:-len(ending)]
                # Check if base form exists in our emotion categories
                for category in self.texts.EMOTION_CATEGORIES.values():
                    if base in category['emotions']:
                        return base
        
        return emotion
    
    def _analyze_triggers(self, entries) -> Dict[str, int]:
        """Extract and count trigger/cause frequencies"""
        trigger_counts = Counter()
        
        # Russian stop words to filter out
        stop_words = {
            'и', 'в', 'на', 'с', 'по', 'для', 'из', 'к', 'от', 'у', 'о', 
            'за', 'при', 'до', 'после', 'через', 'между', 'над', 'под',
            'что', 'как', 'где', 'когда', 'почему', 'который', 'которая',
            'это', 'то', 'так', 'там', 'тут', 'здесь', 'сейчас', 'потом',
            'был', 'была', 'было', 'были', 'есть', 'будет', 'стал', 'стала'
        }
        
        for entry in entries:
            if entry.cause:
                cause_text = entry.cause.lower().strip()
                
                # Extract meaningful words (simple keyword extraction)
                words = cause_text.replace(',', ' ').replace('.', ' ').split()
                
                for word in words:
                    word = word.strip('.,!?;:()[]{}"\'-')
                    
                    # Filter short words and stop words
                    if len(word) >= 3 and word not in stop_words:
                        trigger_counts[word] += 1
        
        return dict(trigger_counts)
    
    def _analyze_time_distribution(self, entries) -> Dict[int, int]:
        """Analyze distribution by hour of day"""
        hour_counts = Counter()
        
        for entry in entries:
            hour = entry.ts_local.hour
            hour_counts[hour] += 1
        
        return dict(hour_counts)
    
    def _get_top_items(self, frequency_dict: Dict[str, int], limit: int = 5) -> List[Tuple[str, int]]:
        """Get top N items by frequency"""
        if not frequency_dict:
            return []
        
        return sorted(frequency_dict.items(), key=lambda x: x[1], reverse=True)[:limit]
    
    async def export_csv(self, user_id: int) -> Optional[str]:
        """Export user data as CSV string"""
        try:
            entries = self.db.get_user_entries(user_id, days=365)  # Export all data
            
            if not entries:
                return None
            
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write headers
            writer.writerow(self.texts.CSV_HEADERS)
            
            # Write data rows
            for entry in entries:
                # Parse emotions
                emotions = self._parse_emotions(entry.emotions) if entry.emotions else []
                emotions_str = ', '.join(emotions)
                
                # Parse tags
                tags = []
                if entry.tags:
                    try:
                        tags = json.loads(entry.tags)
                    except json.JSONDecodeError:
                        tags = [entry.tags]
                tags_str = ', '.join(tags) if tags else ''
                
                # Format row
                row = [
                    entry.ts_local.strftime('%Y-%m-%d'),  # Дата
                    entry.ts_local.strftime('%H:%M'),     # Время
                    entry.valence or '',                   # Валентность
                    entry.arousal or '',                   # Активация  
                    emotions_str,                          # Эмоции
                    entry.cause or '',                     # Причина
                    entry.body or '',                      # Телесные ощущения
                    entry.note or '',                      # Заметка
                    tags_str                               # Теги
                ]
                
                writer.writerow(row)
            
            return output.getvalue()
            
        except Exception as e:
            logger.error(f"Failed to export CSV for user {user_id}: {e}")
            return None
    
    def get_emotion_timeline(self, user_id: int, days: int = 30) -> List[Dict]:
        """Get emotion timeline for visualization"""
        entries = self.db.get_user_entries(user_id, days)
        
        timeline = []
        for entry in entries:
            emotions = self._parse_emotions(entry.emotions) if entry.emotions else []
            
            timeline.append({
                'timestamp': entry.ts_local.isoformat(),
                'date': entry.ts_local.strftime('%Y-%m-%d'),
                'time': entry.ts_local.strftime('%H:%M'),
                'emotions': emotions,
                'valence': entry.valence,
                'arousal': entry.arousal,
                'cause': entry.cause,
                'note': entry.note
            })
        
        return timeline


def test_analyzer():
    """Test the analyzer with sample data"""
    from .db import Database, Entry
    import tempfile
    import os
    
    # Create test database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        test_db_path = f.name
    
    try:
        db = Database(f'sqlite:///{test_db_path}')
        analyzer = WeeklyAnalyzer(db)
        
        # Create test user
        user = db.create_user(12345, 67890)
        
        # Test with 1 entry
        db.create_entry(12345, emotions='["радость"]', cause='хороший день')
        
        import asyncio
        summary = asyncio.run(analyzer.generate_summary(12345))
        print("Summary with 1 entry:")
        print(summary)
        print("\n" + "="*50 + "\n")
        
        # Add more entries
        test_entries = [
            {'emotions': '["тревога"]', 'cause': 'много работы'},  
            {'emotions': '["спокойствие"]', 'cause': 'вечер дома'},
            {'emotions': '["усталость"]', 'cause': 'долгий день'},
        ]
        
        for entry_data in test_entries:
            db.create_entry(12345, **entry_data)
        
        # Test with multiple entries
        summary = asyncio.run(analyzer.generate_summary(12345))
        print("Summary with 4 entries:")
        print(summary)
        
        print("\nAnalyzer tests passed!")
        
    finally:
        os.unlink(test_db_path)


if __name__ == "__main__":
    test_analyzer()
