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
        """Generate weekly summary for user"""
        try:
            entries = self.db.get_user_entries(user_id, days)
            
            if len(entries) < 3:  # Need minimum data for meaningful analysis
                return self.texts.NO_DATA_MESSAGE
            
            # Analyze emotion frequencies
            emotion_freq = self._analyze_emotions(entries)
            top_emotions = self._get_top_items(emotion_freq, limit=5)
            
            # Analyze trigger/cause frequencies  
            trigger_freq = self._analyze_triggers(entries)
            top_triggers = self._get_top_items(trigger_freq, limit=5)
            
            # Analyze time patterns
            time_dist = self._analyze_time_distribution(entries)
            peak_hour = max(time_dist.items(), key=lambda x: x[1])[0] if time_dist else 12
            peak_period = get_time_period_text(peak_hour)
            
            # Generate insights
            insights = generate_insight(top_emotions, top_triggers, peak_hour)
            
            # Format summary
            summary = self.texts.WEEKLY_SUMMARY_TEMPLATE.format(
                top_emotions=format_emotion_list(top_emotions),
                top_triggers=format_emotion_list(top_triggers),
                peak_hours=f"{peak_hour:02d}:00 ({peak_period})",
                total_entries=len(entries),
                insights=insights
            )
            
            return summary
            
        except Exception as e:
            logger.error(f"Failed to generate summary for user {user_id}: {e}")
            return "Не удалось сформировать сводку. Попробуйте позже."
    
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
    
    def _generate_mood_insights(self, entries) -> List[str]:
        """Generate specific mood insights based on patterns"""
        insights = []
        
        if len(entries) < 7:
            return insights
        
        # Analyze weekly patterns
        weekday_moods = {}
        weekend_moods = {}
        
        for entry in entries:
            weekday = entry.ts_local.weekday()  # 0=Monday, 6=Sunday
            emotions = self._parse_emotions(entry.emotions) if entry.emotions else []
            
            if weekday >= 5:  # Weekend (Saturday, Sunday)
                weekend_moods.setdefault(weekday, []).extend(emotions)
            else:  # Weekday
                weekday_moods.setdefault(weekday, []).extend(emotions)
        
        # Compare weekend vs weekday mood
        weekend_emotions = []
        for day_emotions in weekend_moods.values():
            weekend_emotions.extend(day_emotions)
        
        weekday_emotions = []
        for day_emotions in weekday_moods.values():
            weekday_emotions.extend(day_emotions)
        
        # Simple sentiment analysis
        positive_emotions = {'радость', 'счастье', 'удовлетворение', 'спокойствие', 'энергия'}
        negative_emotions = {'тревога', 'грусть', 'злость', 'усталость', 'раздражение'}
        
        weekend_positive = sum(1 for e in weekend_emotions if e in positive_emotions)
        weekend_negative = sum(1 for e in weekend_emotions if e in negative_emotions)
        
        weekday_positive = sum(1 for e in weekday_emotions if e in positive_emotions)
        weekday_negative = sum(1 for e in weekday_emotions if e in negative_emotions)
        
        # Generate insights
        if weekend_positive > weekday_positive * 1.5:
            insights.append("По выходным настроение заметно лучше. Что из 'выходного режима' можно привнести в будни?")
        
        if weekday_negative > weekend_negative * 1.5:
            insights.append("В будни чаще проявляются негативные эмоции. Возможно, стоит пересмотреть рабочий график или добавить больше отдыха?")
        
        return insights
    
    def _calculate_valence_arousal_stats(self, entries) -> Dict[str, float]:
        """Calculate Russell's Circumplex statistics if available"""
        valences = [e.valence for e in entries if e.valence is not None]
        arousals = [e.arousal for e in entries if e.arousal is not None]
        
        stats = {}
        
        if valences:
            stats['avg_valence'] = sum(valences) / len(valences)
            stats['valence_trend'] = 'положительная' if stats['avg_valence'] > 0 else 'отрицательная'
        
        if arousals:
            stats['avg_arousal'] = sum(arousals) / len(arousals)  
            stats['arousal_trend'] = 'высокая' if stats['avg_arousal'] > 0 else 'низкая'
        
        return stats
    
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
    from db import Database, Entry
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
        
        # Create test entries
        test_entries = [
            {'emotions': '["радость", "удовлетворение"]', 'cause': 'закончил проект'},
            {'emotions': '["тревога"]', 'cause': 'много работы'},  
            {'emotions': '["спокойствие"]', 'cause': 'вечер дома'},
            {'emotions': '["усталость"]', 'cause': 'долгий день'},
        ]
        
        for entry_data in test_entries:
            db.create_entry(12345, **entry_data)
        
        # Test summary generation
        import asyncio
        summary = asyncio.run(analyzer.generate_summary(12345))
        print("Generated summary:")
        print(summary)
        
        # Test CSV export
        csv_data = asyncio.run(analyzer.export_csv(12345))
        print("\nCSV export sample:")
        print(csv_data[:200] + "...")
        
        print("\nAnalyzer tests passed!")
        
    finally:
        os.unlink(test_db_path)


if __name__ == "__main__":
    test_analyzer()
