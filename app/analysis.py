#!/usr/bin/env python3
"""
Weekly Analysis and Export for EmoJournal Bot
Generates insights and CSV exports based on user data
FIXED: Corrected emotion categorization logic
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
    """Analyzes user emotion data and generates insights with correct categorization"""
    
    # ИСПРАВЛЕНИЕ: Четкие списки эмоций для каждой группы (в нижнем регистре для точного сравнения)
    EMOTION_GROUPS = {
        'growth': {
            'name': '🌱 Эмоции восстановления и роста',
            'emotions': {
                # Радость/Удовлетворение
                'радость', 'счастье', 'восторг', 'удовлетворение', 'благодарность', 
                'вдохновение', 'эйфория', 'блаженство', 'ликование', 'восхищение', 'умиление',
                # Интерес/Любопытство
                'интерес', 'любопытство', 'увлечённость', 'предвкушение', 'азарт', 
                'энтузиазм', 'воодушевление',
                # Спокойствие/Умиротворение
                'спокойствие', 'умиротворение', 'расслабленность', 'безмятежность', 
                'принятие', 'гармония', 'баланс', 'центрированность', 'покой'
            }
        },
        'tension': {
            'name': '🌪 Эмоции напряжения и сигнала',
            'emotions': {
                # Тревога/Беспокойство
                'тревога', 'беспокойство', 'нервозность', 'волнение', 'напряжение', 
                'страх', 'паника', 'опасения', 'встревоженность',
                # Грусть/Печаль
                'грусть', 'печаль', 'тоска', 'уныние', 'разочарование', 'сожаление', 
                'меланхолия', 'горе', 'скорбь', 'подавленность',
                # Злость/Раздражение
                'злость', 'раздражение', 'гнев', 'возмущение', 'обида', 'фрустрация', 
                'досада', 'негодование', 'ярость', 'недовольство',
                # Стыд/Вина
                'стыд', 'вина', 'смущение', 'неловкость', 'самокритика', 'раскаяние', 
                'угрызения совести',
                # Усталость/Истощение
                'усталость', 'истощение', 'вялость', 'апатия', 'безразличие', 
                'выгорание', 'изнеможение', 'опустошённость'
            }
        },
        'neutral': {
            'name': '⚖ Нейтральные/прочие состояния',
            'emotions': {
                # Энергия/Активность
                'оживление', 'энергия', 'бодрость', 'живость', 'активность', 
                'подъём', 'драйв', 'динамизм'
            }
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
    
    def _get_emotion_group(self, emotion: str) -> str:
        """ИСПРАВЛЕНИЕ: Определить группу эмоции по четким спискам"""
        if not emotion:
            return 'neutral'
        
        # Нормализуем эмоцию
        emotion_normalized = self._normalize_emotion(emotion)
        if not emotion_normalized:
            return 'neutral'
        
        emotion_clean = emotion_normalized.lower().strip()
        
        # ИСПРАВЛЕНИЕ: Проверяем в каждой группе, используя set для быстрого поиска
        for group_key, group_data in self.EMOTION_GROUPS.items():
            if emotion_clean in group_data['emotions']:
                return group_key
        
        # Если не найдено - нейтральная
        return 'neutral'
    
    def _analyze_emotions_by_groups(self, entries) -> Dict:
        """Анализ эмоций по новым группам"""
        # Группируем эмоции
        grouped_emotions = {
            'growth': defaultdict(int),
            'tension': defaultdict(int), 
            'neutral': defaultdict(int)
        }
        
        for entry in entries:
            if entry.emotions:
                emotions = self._parse_emotions(entry.emotions)
                for emotion in emotions:
                    normalized = self._normalize_emotion(emotion)
                    if normalized:
                        group = self._get_emotion_group(normalized)
                        grouped_emotions[group][normalized] += 1
        
        # Формируем результат
        result = {}
        for group_key, group_info in self.EMOTION_GROUPS.items():
            emotions_in_group = dict(grouped_emotions[group_key])
            total_count = sum(emotions_in_group.values())
            top_emotions = sorted(emotions_in_group.items(), key=lambda x: x[1], reverse=True)[:5]
            
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
                
                # Определяем к какой группе относится эта запись
                emotion_groups = []
                for emotion in emotions:
                    normalized = self._normalize_emotion(emotion)
                    if normalized:
                        group = self._get_emotion_group(normalized)
                        emotion_groups.append(group)
                
                # Приоритет: tension > growth > neutral
                if 'tension' in emotion_groups:
                    grouped_triggers['tension'].append(entry.cause.strip())
                elif 'growth' in emotion_groups:
                    grouped_triggers['growth'].append(entry.cause.strip())
                else:
                    grouped_triggers['neutral'].append(entry.cause.strip())
        
        # Формируем результат
        result = {}
        trigger_names = {
            'growth': '🌱 Что спровоцировало эмоции восстановления и роста',
            'tension': '🌪 Триггеры эмоций напряжения и сигнала',
            'neutral': '⚖ Триггеры нейтральных эмоций'
        }
        
        for group_key in ['growth', 'tension', 'neutral']:
            triggers = grouped_triggers[group_key]
            result[group_key] = {
                'name': trigger_names[group_key],
                'triggers': triggers,
                'count': len(triggers)
            }
        
        return result
    
    def _format_enhanced_summary(self, emotion_analysis, trigger_analysis, peak_hour, peak_period, total_entries, insights):
        """Форматирование новой сводки"""
        
        summary_parts = [
            "📊 <b>Твоя неделя в эмоциях</b>\n",
            "<b>🎭 Эмоции по группам:</b>\n"
        ]
        
        # Формируем блоки эмоций (показываем все группы, даже с 0)
        for group_key in ['growth', 'tension', 'neutral']:
            group_data = emotion_analysis[group_key]
            
            if group_data['total_count'] > 0:
                top_emotions_str = ', '.join([f"{emotion} ({count})" for emotion, count in group_data['top_emotions']])
                summary_parts.append(f"<b>{group_data['name']}:</b> {group_data['total_count']} раз")
                summary_parts.append(f"{top_emotions_str}\n")
            else:
                summary_parts.append(f"<b>{group_data['name']}:</b> 0 раз\n")
        
        summary_parts.append("<b>🔍 Что влияло на эмоции:</b>\n")
        
        # Формируем блоки триггеров (только если есть триггеры)
        for group_key in ['growth', 'tension', 'neutral']:
            group_data = trigger_analysis[group_key]
            if group_data['count'] > 0:
                # Показываем до 5 триггеров
                sample_triggers = group_data['triggers'][:5]
                triggers_formatted = []
                for trigger in sample_triggers:
                    triggers_formatted.append(f"• {trigger}")
                
                triggers_str = '\n'.join(triggers_formatted)
                if len(group_data['triggers']) > 5:
                    triggers_str += f"\n<i>(и ещё {len(group_data['triggers']) - 5})</i>"
                
                summary_parts.append(f"<b>{group_data['name']}:</b>")
                summary_parts.append(f"{triggers_str}\n")
        
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
        elif len(entries) >= 2:
            # Простые инсайты для небольшого количества записей
            if growth_count > tension_count:
                insights.append("✨ Здорово, что преобладают позитивные эмоции!")
            elif tension_count > growth_count:
                insights.append("🤗 Замечать сложные эмоции — важный шаг к их пониманию.")
        
        return "\n\n".join(insights) if insights else ""
    
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
        """ИСПРАВЛЕНИЕ: Normalize emotion to base form (enhanced Russian stemming)"""
        if not emotion or not isinstance(emotion, str):
            return None
            
        emotion = emotion.strip().lower()
        
        if len(emotion) < 2:
            return None
        
        # ИСПРАВЛЕНИЕ: Расширенное русское нормирование эмоций
        emotion_mapping = {
            # Радость family
            'радостный': 'радость', 'радостная': 'радость', 'радостное': 'радость', 'радостные': 'радость',
            'счастливый': 'счастье', 'счастливая': 'счастье', 'счастливое': 'счастье', 'счастливые': 'счастье',
            'довольный': 'удовлетворение', 'довольная': 'удовлетворение', 'довольное': 'удовлетворение',
            
            # Тревога family  
            'тревожный': 'тревога', 'тревожная': 'тревога', 'тревожное': 'тревога', 'тревожные': 'тревога',
            'беспокойный': 'беспокойство', 'беспокойная': 'беспокойство', 'беспокойное': 'беспокойство',
            'нервный': 'нервозность', 'нервная': 'нервозность', 'нервное': 'нервозность',
            'взволнованный': 'волнение', 'взволнованная': 'волнение',
            
            # Грусть family
            'грустный': 'грусть', 'грустная': 'грусть', 'грустное': 'грусть', 'грустные': 'грусть',
            'печальный': 'печаль', 'печальная': 'печаль', 'печальное': 'печаль',
            'расстроенный': 'расстройство', 'расстроенная': 'расстройство',
            
            # Злость family
            'злой': 'злость', 'злая': 'злость', 'злое': 'злость', 'злые': 'злость',
            'раздражённый': 'раздражение', 'раздражённая': 'раздражение', 'раздраженный': 'раздражение',
            'сердитый': 'злость', 'сердитая': 'злость',
            
            # Усталость family
            'усталый': 'усталость', 'усталая': 'усталость', 'усталое': 'усталость',
            'уставший': 'усталость', 'уставшая': 'усталость',
            'измученный': 'истощение', 'измученная': 'истощение',
            
            # Спокойствие family
            'спокойный': 'спокойствие', 'спокойная': 'спокойствие', 'спокойное': 'спокойствие',
            'расслабленный': 'расслабленность', 'расслабленная': 'расслабленность',
            
            # Интерес family
            'интересно': 'интерес', 'заинтересованный': 'интерес', 'заинтересованная': 'интерес',
            'любопытный': 'любопытство', 'любопытная': 'любопытство',
        }
        
        # Direct mapping
        if emotion in emotion_mapping:
            return emotion_mapping[emotion]
        
        # ИСПРАВЛЕНИЕ: Улучшенное удаление русских окончаний
        endings_to_remove = [
            'ый', 'ая', 'ое', 'ые', 'ой', 'ей', 'их', 'ым', 'ыми', 'ую', 'ую', 'ого', 'ую',
            'ён', 'на', 'но', 'ны', 'ённый', 'енный', 'нный'
        ]
        
        for ending in endings_to_remove:
            if emotion.endswith(ending) and len(emotion) > len(ending) + 2:
                base = emotion[:-len(ending)]
                
                # Проверяем, есть ли базовая форма в наших эмоциональных группах
                for group_data in self.EMOTION_GROUPS.values():
                    if base in group_data['emotions']:
                        return base
        
        # Возвращаем как есть, если не смогли нормализовать
        return emotion
    
    def _analyze_time_distribution(self, entries) -> Dict[int, int]:
        """Analyze distribution by hour of day"""
        hour_counts = Counter()
        
        for entry in entries:
            hour = entry.ts_local.hour
            hour_counts[hour] += 1
        
        return dict(hour_counts)
    
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
        
        # Test emotion grouping
        test_emotions = ['радость', 'тревога', 'спокойствие', 'усталость', 'возмущение', 'апатия']
        
        print("Testing emotion grouping:")
        for emotion in test_emotions:
            group = analyzer._get_emotion_group(emotion)
            print(f"  {emotion} -> {group}")
        
        # Add test entries with different emotion groups
        test_entries = [
            {'emotions': '["радость"]', 'cause': 'закончил проект'},
            {'emotions': '["тревога"]', 'cause': 'много работы'},  
            {'emotions': '["спокойствие"]', 'cause': 'вечер дома'},
            {'emotions': '["усталость"]', 'cause': 'долгий день'},
            {'emotions': '["возмущение"]', 'cause': 'пробка на дороге'},
        ]
        
        for entry_data in test_entries:
            db.create_entry(12345, **entry_data)
        
        import asyncio
        summary = asyncio.run(analyzer.generate_summary(12345))
        print("\nFixed summary:")
        print(summary)
        
        print("\nFixed analyzer tests completed!")
        
    finally:
        os.unlink(test_db_path)


if __name__ == "__main__":
    test_analyzer()
