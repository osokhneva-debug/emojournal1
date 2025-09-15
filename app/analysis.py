#!/usr/bin/env python3
"""
Weekly Analysis and Export for EmoJournal Bot
Generates insights and CSV exports based on user data
Enhanced with emotion categorization
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import json
import csv
import io
from collections import Counter, defaultdict

from .i18n import Texts, format_emotion_list, get_time_period_text, generate_insight

logger = logging.getLogger(__name__)

class WeeklyAnalyzer:
    """Analyzes user emotion data and generates insights with categorization"""
    
    # Новые категории эмоций
    EMOTION_GROUPS = {
        'growth': {
            'name': '🌱 Эмоции восстановления и роста',
            'categories': ['joy', 'interest', 'calm']
        },
        'tension': {
            'name': '🌪 Эмоции напряжения и сигнала', 
            'categories': ['anxiety', 'sadness', 'anger', 'shame', 'fatigue']
        },
        'neutral': {
            'name': '⚖ Нейтральные / прочие состояния',
            'categories': ['excitement']  # и любые другие
        }
    }
    
    def __init__(self, db):
        self.db = db
        self.texts = Texts()
    
    async def generate_summary(self, user_id: int, days: int = 7) -> str:
        """Generate enhanced summary with emotion grouping"""
        try:
            entries = self.db.get_user_entries(user_id, days)
            
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
            emotion_analysis = self._analyze_emotions_by_groups(entries)
            trigger_analysis = self._analyze_triggers_by_groups(entries)
            
            time_dist = self._analyze_time_distribution(entries)
            peak_hour = max(time_dist.items(), key=lambda x: x[1])[0] if time_dist else 12
            peak_period = get_time_period_text(peak_hour)
            
            # Генерируем инсайты
            insights = self._generate_enhanced_insights(entries, emotion_analysis, trigger_analysis)
            
            # Формируем новую сводку
            summary = self._format_enhanced_summary(
                emotion_analysis, 
                trigger_analysis, 
                peak_hour, 
                peak_period, 
                len(entries), 
                insights
            )
            
            return summary
            
        except Exception as e:
            logger.error(f"Failed to generate summary for user {user_id}: {e}")
            return "Не удалось сформировать сводку. Попробуйте позже."
    
    def _analyze_emotions_by_groups(self, entries) -> Dict:
        """Анализ эмоций по новым группам"""
        # Сначала получаем все эмоции как раньше
        emotion_freq = self._analyze_emotions(entries)
        
        # Группируем по категориям
        grouped_emotions = {
            'growth': defaultdict(int),
            'tension': defaultdict(int), 
            'neutral': defaultdict(int)
        }
        
        # Подсчитываем эмоции по группам
        for emotion, count in emotion_freq.items():
            group = self._get_emotion_group(emotion)
            grouped_emotions[group][emotion] += count
        
        # Формируем результат
        result = {}
        for group_key, group_info in self.EMOTION_GROUPS.items():
            emotions_in_group = dict(grouped_emotions[group_key])
            total_count = sum(emotions_in_group.values())
            top_emotions = sorted(emotions_in_group.items(), key=lambda x: x[1], reverse=True)[:3]
            
            result[group_key] = {
                'name': group_info['name'],
                'total_count': total_count,
                'emotions': emotions_in_group,
                'top_emotions': top_emotions
            }
        
        return result
    
    def _analyze_triggers_by_groups(self, entries) -> Dict:
        """Анализ триггеров по группам эмоций"""
        # Собираем триггеры для каждой группы эмоций
        grouped_triggers = {
            'growth': [],
            'tension': [],
            'neutral': []
        }
        
        for entry in entries:
            if entry.cause and entry.emotions:
                emotions = self._parse_emotions(entry.emotions)
                
                # Определяем группу эмоций для этой записи
                emotion_groups = [self._get_emotion_group(emotion) for emotion in emotions]
                
                # Если есть эмоции напряжения, триггер относим к напряжению
                if 'tension' in emotion_groups:
                    grouped_triggers['tension'].append(entry.cause)
                # Если есть эмоции роста, триггер относим к росту
                elif 'growth' in emotion_groups:
                    grouped_triggers['growth'].append(entry.cause)
                # Иначе к нейтральным
                else:
                    grouped_triggers['neutral'].append(entry.cause)
        
        # Формируем результат
        result = {}
        for group_key, group_info in self.EMOTION_GROUPS.items():
            triggers = grouped_triggers[group_key]
            result[group_key] = {
                'name': group_info['name'].replace('Эмоции', 'Триггеры эмоций'),
                'triggers': triggers,
                'count': len(triggers)
            }
        
        return result
    
    def _get_emotion_group(self, emotion: str) -> str:
        """Определить группу эмоции"""
        emotion = emotion.lower().strip()
        
        # Проверяем в каждой категории
        for group_key, group_info in self.EMOTION_GROUPS.items():
            for category in group_info['categories']:
                category_emotions = self.texts.EMOTION_CATEGORIES.get(category, {}).get('emotions', [])
                if emotion in category_emotions:
                    return group_key
        
        # Если не найдено - нейтральная
        return 'neutral'
    
    def _format_enhanced_summary(self, emotion_analysis, trigger_analysis, peak_hour, peak_period, total_entries, insights):
        """Форматирование новой сводки"""
        
        # Формируем блоки эмоций
        emotion_blocks = []
        for group_key in ['growth', 'tension', 'neutral']:
            group_data = emotion_analysis[group_key]
            if group_data['total_count'] > 0:
                top_emotions_str = ', '.join([f"{emotion} ({count})" for emotion, count in group_data['top_emotions']])
                emotion_blocks.append(f"<b>{group_data['name']}:</b> {group_data['total_count']} раз\n{top_emotions_str}")
        
        # Формируем блоки триггеров
        trigger_blocks = []
        for group_key in ['growth', 'tension', 'neutral']:
            group_data = trigger_analysis[group_key]
            if group_data['count'] > 0:
                # Берем первые 3 триггера как примеры
                sample_triggers = group_data['triggers'][:3]
                triggers_str = '; '.join(sample_triggers)
                if len(group_data['triggers']) > 3:
                    triggers_str += f" (и ещё {len(group_data['triggers']) - 3})"
                trigger_blocks.append(f"<b>{group_data['name']}:</b>\n{triggers_str}")
        
        # Собираем итоговую сводку
        summary_parts = [
            "📊 <b>Твоя неделя в эмоциях</b>\n"
        ]
        
        if emotion_blocks:
            summary_parts.append("<b>🎭 Эмоции по группам:</b>")
            summary_parts.extend(emotion_blocks)
            summary_parts.append("")
        
        if trigger_blocks:
            summary_parts.append("<b>🔍 Что влияло на эмоции:</b>")
            summary_parts.extend(trigger_blocks)
            summary_parts.append("")
        
        summary_parts.extend([
            f"<b>⏰ Пик активности:</b> {peak_hour:02d}:00 ({peak_period})",
            f"<b>📈 Всего записей:</b> {total_entries}",
            ""
        ])
        
        if insights:
            summary_parts.append(insights)
            summary_parts.append("")
        
        summary_parts.append("<i>Хочешь подробности? Используй /export для CSV-файла.</i>")
        
        return "\n".join(summary_parts)
    
    def _generate_enhanced_insights(self, entries, emotion_analysis, trigger_analysis):
        """Генерация инсайтов на основе новой группировки"""
        insights = []
        
        # Анализ баланса эмоций
        growth_count = emotion_analysis['growth']['total_count']
        tension_count = emotion_analysis['tension']['total_count']
        total_emotional = growth_count + tension_count
        
        if total_emotional > 0:
            growth_ratio = growth_count / total_emotional
            
            if growth_ratio >= 0.7:
                insights.append("✨ <b>Отличный баланс!</b> Преобладают эмоции восстановления и роста.")
            elif growth_ratio >= 0.4:
                insights.append("⚖️ <b>Сбалансированная неделя:</b> эмоции роста и напряжения в равновесии.")
            else:
                insights.append("🤗 <b>Непростая неделя:</b> много эмоций напряжения. Это нормально - они тоже важны для понимания себя.")
        
        # Анализ специфических паттернов
        if len(entries) >= 5:
            # Анализ триггеров роста
            growth_triggers = trigger_analysis['growth']['triggers']
            if len(growth_triggers) >= 2:
                insights.append(f"💡 <b>Что тебя вдохновляет:</b> обрати внимание на ситуации, которые приносят эмоции роста.")
            
            # Анализ триггеров напряжения
            tension_triggers = trigger_analysis['tension']['triggers']
            if len(tension_triggers) >= 2:
                insights.append(f"🛡️ <b>Зоны внимания:</b> стоит подумать о стратегиях работы с повторяющимися стрессорами.")
        
        return "\n\n".join(insights) if insights else ""
    
    def _generate_simple_insights(self, entries, emotion_analysis) -> str:
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
        
        # Быстрый анализ групп эмоций
        growth_count = emotion_analysis['growth']['total_count']
        tension_count = emotion_analysis['tension']['total_count']
        
        if growth_count > tension_count:
            insights.append("✨ Здорово, что преобладают позитивные эмоции!")
        elif tension_count > growth_count:
            insights.append("🤗 Замечать сложные эмоции — важный шаг к их пониманию.")
        
        return "\n\n".join(insights)
    
    # Оставляем старые методы для совместимости, но используем новую логику
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
        
        # Add test entries with different emotion groups
        test_entries = [
            {'emotions': '["радость"]', 'cause': 'закончил проект'},
            {'emotions': '["тревога"]', 'cause': 'много работы'},  
            {'emotions': '["спокойствие"]', 'cause': 'вечер дома'},
            {'emotions': '["усталость"]', 'cause': 'долгий день'},
            {'emotions': '["интерес"]', 'cause': 'новая книга'},
        ]
        
        for entry_data in test_entries:
            db.create_entry(12345, **entry_data)
        
        import asyncio
        summary = asyncio.run(analyzer.generate_summary(12345))
        print("Enhanced summary:")
        print(summary)
        
        print("\nEnhanced analyzer tests passed!")
        
    finally:
        os.unlink(test_db_path)


if __name__ == "__main__":
    test_analyzer()
