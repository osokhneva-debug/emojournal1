#!/usr/bin/env python3
"""
Internationalization texts for EmoJournal Bot (Russian language)
Based on established emotion theories and NVC principles
Updated with new features: interactive summaries and settings
"""

class Texts:
    """
    Text constants based on emotion research:
    - Russell's Circumplex Model (valence × arousal)
    - Plutchik's Wheel of Emotions (basic emotions + gradations)
    - NVC Feelings Inventory (judgment-free feeling words)
    - Affect Labeling research (verbalization reduces intensity)
    - Cognitive Appraisal Theory (context influences emotions)
    """
    
    # Onboarding and help - UPDATED
    ONBOARDING = """
🎭 <b>Добро пожаловать в EmoJournal!</b>

Я помогу тебе отслеживать эмоции и находить закономерности в настроении.

<b>Как это работает:</b>
• 4 раза в день я спрошу, как дела (в 9:00, 13:00, 17:00, 21:00)
• Ты можешь ответить или пропустить
• Каждое воскресенье в 21:00 пришлю сводку за неделю (можно отключить в /settings)
• Можешь записать эмоцию в любой момент: /note
• Смотри сводки за любой период: /summary
• Настрой свой часовой пояс: /timezone

<b>Научная основа:</b>
Простое называние эмоций (affect labeling) снижает их интенсивность и помогает лучше понимать себя.

<b>Приватность:</b>
Все данные хранятся локально на защищенном сервере, только у тебя есть доступ. Экспорт доступен по команде /export, удаление — /delete_me.

Начнём? Используй /help для списка команд или /note чтобы записать эмоцию прямо сейчас.
"""
    
    # UPDATED HELP
    HELP = """
<b>🎭 EmoJournal — твой эмоциональный дневник</b>

<b>Команды:</b>
/note — записать эмоцию сейчас
/summary — интерактивные сводки за любой период
/settings — настройки автосаммари и времени
/export — выгрузка данных в CSV  
/timezone — настройка часового пояса
/pause — приостановить уведомления
/resume — возобновить уведомления
/delete_me — удалить все данные
/stats — общая статистика бота

<b>Автоматические саммари:</b>
Каждое воскресенье в 21:00 (или в выбранное тобой время) получай сводку за неделю. Можно отключить в /settings.

<b>Интерактивные сводки:</b>
Команда /summary покажет кнопки выбора периода: 7 дней, 2 недели, месяц, 3 месяца или свой период.

<b>Как это помогает:</b>
Исследования показывают, что вербализация эмоций (affect labeling) активирует префронтальную кору и снижает активность миндалевидного тела, что помогает регулировать эмоции.

Отслеживание закономерностей (время, триггеры, контекст) развивает эмоциональную осознанность.

<b>Не заменяет:</b>
Помощь специалистов при серьёзных проблемах с психическим здоровьем.
    """
    
    # Emotion check-in prompts
    EMOTION_PING = """
🌟 Как ты сейчас?

Если хочется — выбери 1-2 слова или просто опиши своими словами.

<i>Сам факт, что ты это заметишь и назовёшь, — уже шаг к ясности.</i>
    """
    
    EMOTION_QUESTION = """
😊 Как ты сейчас себя чувствуешь?

Можешь выбрать из подсказок или описать своими словами — как удобно.
    """
    
    INTENSITY_QUESTION = """
По шкале от 0 до 10, насколько интенсивно это ощущается?

<i>0 — едва заметно, 10 — очень сильно</i>

Или просто пропусти, отправив любой текст.
    """
    
    BODY_QUESTION = """
Есть ли телесные ощущения?

Например:
• Напряжение в плечах или шее
• Тепло в груди  
• Сжатие в животе
• Лёгкость или тяжесть

Можешь пропустить, если не замечаешь.
    """
    
    CAUSE_QUESTION = """
Что, как тебе кажется, поспособствовало этим эмоциям?

Это может быть:
• Конкретное событие
• Мысль или воспоминание  
• Взаимодействие с человеком
• Место или обстановка
• Усталость или физическое состояние

Или просто «не знаю» — это тоже нормально.
    """
    
    NOTE_QUESTION = """
Хочешь добавить заметку на будущее?

Что-то, что поможет лучше понять эту ситуацию при просмотре сводки.
    """
    
    # Responses and acknowledgments  
    THANK_YOU = """
✨ <b>Спасибо!</b>

Уже сам факт, что ты это заметил(а) и назвал(а), — шаг к ясности.

<i>Исследования показывают, что называние эмоций помогает их регулировать.</i>
    """
    
    SNOOZE_RESPONSE = "Напомню через 15 минут ⏰"
    
    SKIP_RESPONSE = "Хорошо, сегодня больше не побеспокою 😊"
    
    # NEW: Summary interface texts
    SUMMARY_PERIOD_SELECTION = """
📊 За какой период показать сводку?

Выбери готовый период или укажи свой:
    """
    
    SUMMARY_GENERATING = "📊 Генерирую сводку..."
    
    SUMMARY_CUSTOM_PERIOD_REQUEST = """
📊 Введите количество дней для анализа (от 1 до 90):

Например: 14 (для двух недель)
    """
    
    SUMMARY_PERIOD_ERROR = "Количество дней должно быть от 1 до 90. Попробуйте еще раз."
    
    # NEW: Settings texts
    SETTINGS_MAIN = """
⚙️ <b>Настройки EmoJournal</b>

📅 <b>Автоматические саммари:</b> {weekly_status}
🕘 <b>Время отправки:</b> каждое воскресенье в {hour:02d}:00

Выберите что хотите изменить:
    """
    
    SETTINGS_WEEKLY_ENABLED = "✅ Включены"
    SETTINGS_WEEKLY_DISABLED = "❌ Отключены"
    
    SETTINGS_TIME_SELECTION = """
🕘 Выберите время для получения еженедельных саммари:

Саммари будут приходить каждое воскресенье в выбранное время.
    """
    
    SETTINGS_SAVED = "✅ Настройки сохранены!"
    
    SETTINGS_ERROR = "Произошла ошибка при изменении настройки."
    
    # Weekly summary template (legacy - сейчас используется новая логика в analysis.py)
    WEEKLY_SUMMARY_TEMPLATE = """
📊 <b>Твоя неделя в эмоциях</b>

<b>🎭 Чаще всего:</b>
{top_emotions}

<b>🔍 Частые причины:</b>  
{top_triggers}

<b>⏰ Пик активности:</b>
{peak_hours}

<b>📈 Всего записей:</b> {total_entries}

{insights}

<i>Хочешь подробности? Используй /export для CSV-файла.</i>
    """
    
    NO_DATA_MESSAGE = """
📭 У тебя пока нет записей эмоций.

Используй /note чтобы записать свою первую эмоцию, или просто отвечай на мои ежедневные вопросы в 9:00, 13:00, 17:00 и 21:00!
    """
    
    NO_DATA_FOR_PERIOD = "📭 За этот период записей нет."
    
    # NEW: Automatic summary texts
    AUTO_SUMMARY_HEADER = "📅 <b>Автоматическая сводка за неделю</b>"
    
    AUTO_SUMMARY_INTRO = """
📅 <b>Твоя неделя подошла к концу!</b>

Вот что удалось отследить за последние 7 дней:
    """
    
    # Emotion categories (сохраняем для совместимости с интерфейсом)
    EMOTION_CATEGORIES = {
        'joy': {
            'name': 'Радость/Удовлетворение',
            'emotions': [
                'радость', 'счастье', 'восторг', 'удовлетворение', 
                'благодарность', 'вдохновение', 'эйфория', 'блаженство',
                'ликование', 'восхищение', 'умиление'
            ]
        },
        'interest': {
            'name': 'Интерес/Любопытство', 
            'emotions': [
                'интерес', 'любопытство', 'увлечённость', 'восхищение',
                'предвкушение', 'азарт', 'энтузиазм', 'воодушевление'
            ]
        },
        'calm': {
            'name': 'Спокойствие/Умиротворение',
            'emotions': [
                'спокойствие', 'умиротворение', 'расслабленность', 'безмятежность',
                'принятие', 'гармония', 'баланс', 'центрированность', 'покой'
            ]
        },
        'anxiety': {
            'name': 'Тревога/Беспокойство',
            'emotions': [
                'тревога', 'беспокойство', 'нервозность', 'волнение',
                'напряжение', 'страх', 'паника', 'опасения', 'встревоженность'
            ]
        },
        'sadness': {
            'name': 'Грусть/Печаль',
            'emotions': [
                'грусть', 'печаль', 'тоска', 'уныние', 'разочарование',
                'сожаление', 'меланхолия', 'горе', 'скорбь', 'подавленность'
            ]
        },
        'anger': {
            'name': 'Злость/Раздражение',
            'emotions': [
                'злость', 'раздражение', 'гнев', 'возмущение', 'обида',
                'фрустрация', 'досада', 'негодование', 'ярость', 'недовольство'
            ]
        },
        'shame': {
            'name': 'Стыд/Вина',
            'emotions': [
                'стыд', 'вина', 'смущение', 'неловкость', 'сожаление',
                'самокритика', 'раскаяние', 'угрызения совести'
            ]
        },
        'fatigue': {
            'name': 'Усталость/Истощение',
            'emotions': [
                'усталость', 'истощение', 'вялость', 'апатия', 
                'безразличие', 'выгорание', 'изнеможение', 'опустошённость'
            ]
        },
        'excitement': {
            'name': 'Оживление/Энергия',
            'emotions': [
                'оживление', 'энергия', 'бодрость', 'живость',
                'активность', 'подъём', 'драйв', 'динамизм'
            ]
        }
    }
    
    # Contextual prompts for cognitive appraisal
    CONTEXT_PROMPTS = [
        "Что происходило прямо перед этим?",
        "О чём ты думал(а) в этот момент?", 
        "Где ты находился(ась)?",
        "С кем ты был(а) или о ком думал(а)?",
        "Что изменилось в последнее время?",
        "Какие ожидания были у тебя?",
        "Что показалось особенно важным?"
    ]
    
    # Insight templates for weekly analysis
    INSIGHT_TEMPLATES = {
        'work_stress_evening': """
💡 <b>Замечание:</b> Часто тревога проявляется вечером, а триггер связан с работой. 
Возможно, стоит попробовать короткий ритуал "переключения" после рабочего дня?
        """,
        
        'morning_anxiety': """
💡 <b>Замечание:</b> Тревога часто появляется утром. 
Может помочь 2-минутная дыхательная практика или планирование дня с вечера.
        """,
        
        'weekend_joy': """
💡 <b>Замечание:</b> По выходным настроение заметно лучше. 
Что из "выходного режима" можно привнести в будни?
        """,
        
        'social_energy': """
💡 <b>Замечание:</b> Общение с людьми часто даёт энергию. 
Возможно, стоит планировать больше социальных активностей?
        """,
        
        'evening_fatigue': """
💡 <b>Замечание:</b> Усталость накапливается к вечеру. 
Короткие перерывы в течение дня могут помочь сохранить энергию.
        """
    }
    
    # Export CSV headers (Russian)
    CSV_HEADERS = [
        'Дата',
        'Время', 
        'Валентность',
        'Активация',
        'Эмоции',
        'Причина',
        'Телесные ощущения',
        'Заметка',
        'Теги'
    ]
    
    # Command responses
    TIMEZONE_SET = "Часовой пояс установлен: {timezone}"
    TIMEZONE_INVALID = "Неверный часовой пояс. Используйте формат IANA, например: Europe/Moscow, Asia/Yekaterinburg"
    TIMEZONE_CURRENT = "Текущий часовой пояс: {timezone}\n\nДля изменения используйте: /timezone Europe/Moscow"
    
    PAUSE_CONFIRM = "Уведомления приостановлены. Используйте /resume для возобновления."
    RESUME_CONFIRM = "Уведомления возобновлены!"
    
    DELETE_CONFIRM_PROMPT = """
⚠️ Вы уверены, что хотите удалить все свои данные?

Это действие необратимо. Будут удалены:
• Все записи эмоций
• Настройки уведомлений  
• История и статистика
    """
    
    DELETE_SUCCESS = """
Все ваши данные удалены.

Спасибо, что использовали EmoJournal!
Если захотите начать заново — отправьте /start
    """
    
    DELETE_CANCELLED = "Удаление отменено"
    
    EXPORT_NO_DATA = "Пока нет данных для экспорта"
    EXPORT_SUCCESS = "Ваши данные в формате CSV"
    
    # UPDATED STATS TEMPLATE
    STATS_TEMPLATE = """
📊 <b>Статистика EmoJournal:</b>

👥 Всего пользователей: {total_users}
📝 Всего записей: {total_entries}  
📅 Активных за неделю: {active_weekly}
📊 Подписано на саммари: {weekly_summary_users}
    """
    
    # Error messages
    ERROR_RATE_LIMIT = "Слишком много команд. Попробуйте через пару секунд."
    ERROR_GENERIC = "Что-то пошло не так. Попробуйте позже."
    ERROR_NO_USER = "Пользователь не найден. Отправьте /start для регистрации."
    
    # Validation messages
    INTENSITY_INVALID = "Укажите число от 0 до 10, или отправьте любой текст для пропуска."
    
    # Motivational messages for consistency
    CONSISTENCY_MESSAGES = [
        "Отлично! Регулярность — ключ к пониманию своих паттернов.",
        "Здорово, что продолжаешь отслеживать эмоции!",
        "Каждая запись приближает к лучшему пониманию себя.",
        "Ты делаешь важную работу по самопознанию!"
    ]
    
    # Gentle reminders for missed check-ins
    GENTLE_REMINDERS = [
        "Давно не слышал от тебя. Как дела?",
        "Проверяю связь — как настроение сегодня?", 
        "Просто интересуюсь — как ты?"
    ]
    
    # Privacy and data handling
    PRIVACY_NOTICE = """
🔒 <b>О приватности данных:</b>

• Данные хранятся локально на сервере бота
• Никто кроме тебя не имеет к ним доступа
• Можешь экспортировать всё в CSV: /export
• Можешь удалить всё: /delete_me
• Бот не даёт медицинских рекомендаций
• При серьёзных проблемах обратись к специалисту
    """

    # NEW: Period formatting helpers
    PERIOD_NAMES = {
        7: "неделю",
        14: "2 недели", 
        30: "месяц",
        90: "3 месяца"
    }
    
    # NEW: Button texts
    BUTTON_TEXTS = {
        'summary_7_days': "7 дней",
        'summary_14_days': "2 недели", 
        'summary_30_days': "30 дней",
        'summary_90_days': "3 месяца",
        'summary_custom': "Другой период",
        'another_period': "Другой период",
        'export_csv': "📥 Экспорт CSV",
        'settings_close': "💾 Сохранить и закрыть",
        'back_to_settings': "← Назад к настройкам"
    }


def get_random_emotion_prompt():
    """Get random emotion prompt for variety"""
    import random
    
    prompts = [
        "Как ты сейчас?",
        "Что происходит внутри?", 
        "Какое у тебя настроение?",
        "Как дела с эмоциями?",
        "Что чувствуешь прямо сейчас?"
    ]
    
    return random.choice(prompts)


def get_random_context_prompt():
    """Get random context prompt based on cognitive appraisal theory"""
    import random
    
    texts = Texts()
    return random.choice(texts.CONTEXT_PROMPTS)


def get_emotion_by_category(category: str):
    """Get emotions list for specific category"""
    texts = Texts()
    return texts.EMOTION_CATEGORIES.get(category, {}).get('emotions', [])


def format_emotion_list(emotions: list, max_length: int = 100):
    """Format emotion list for display with length limit"""
    if not emotions:
        return "нет данных"
    
    # Sort by frequency if tuple, otherwise alphabetically
    if emotions and isinstance(emotions[0], tuple):
        sorted_emotions = sorted(emotions, key=lambda x: x[1], reverse=True)
        formatted = ", ".join([f"{emotion} ({count})" for emotion, count in sorted_emotions[:5]])
    else:
        sorted_emotions = sorted(emotions)[:5]  
        formatted = ", ".join(sorted_emotions)
    
    if len(formatted) > max_length:
        formatted = formatted[:max_length-3] + "..."
    
    return formatted


def get_time_period_text(hour: int):
    """Get human-readable time period"""
    if 6 <= hour < 12:
        return "утром"
    elif 12 <= hour < 18:
        return "днём"  
    elif 18 <= hour < 23:
        return "вечером"
    else:
        return "ночью"


def get_period_name(days: int) -> str:
    """Get human-readable period name"""
    texts = Texts()
    return texts.PERIOD_NAMES.get(days, f"{days} дней")


def format_settings_text(weekly_enabled: bool, summary_hour: int) -> str:
    """Format settings display text"""
    texts = Texts()
    weekly_status = texts.SETTINGS_WEEKLY_ENABLED if weekly_enabled else texts.SETTINGS_WEEKLY_DISABLED
    
    return texts.SETTINGS_MAIN.format(
        weekly_status=weekly_status,
        hour=summary_hour
    )


def generate_insight(top_emotions: list, top_triggers: list, peak_hour: int):
    """Generate contextual insight based on patterns"""
    texts = Texts()
    
    # Convert to simple lists if tuples
    if top_emotions and isinstance(top_emotions[0], tuple):
        emotions = [e[0] for e in top_emotions[:3]]
    else:
        emotions = top_emotions[:3] if top_emotions else []
    
    if top_triggers and isinstance(top_triggers[0], tuple):
        triggers = [t[0] for t in top_triggers[:3]]  
    else:
        triggers = top_triggers[:3] if top_triggers else []
    
    # Pattern matching for insights
    if any('тревога' in e or 'беспокойство' in e for e in emotions):
        if 6 <= peak_hour < 12:
            return texts.INSIGHT_TEMPLATES['morning_anxiety']
        elif any('работа' in t for t in triggers) and 16 <= peak_hour < 20:
            return texts.INSIGHT_TEMPLATES['work_stress_evening']
    
    if any('усталость' in e or 'истощение' in e for e in emotions):
        if 18 <= peak_hour < 23:
            return texts.INSIGHT_TEMPLATES['evening_fatigue']
    
    if any('радость' in e or 'счастье' in e for e in emotions):
        # Check if weekend pattern exists (simplified)
        return texts.INSIGHT_TEMPLATES['weekend_joy']
    
    if any('люди' in t or 'друзья' in t or 'семья' in t for t in triggers):
        return texts.INSIGHT_TEMPLATES['social_energy']
    
    return ""  # No specific insight


if __name__ == "__main__":
    # Test some functions
    texts = Texts()
    
    print("Emotion categories:")
    for category, data in texts.EMOTION_CATEGORIES.items():
        print(f"- {data['name']}: {len(data['emotions'])} emotions")
    
    print(f"\nRandom emotion prompt: {get_random_emotion_prompt()}")
    print(f"Random context prompt: {get_random_context_prompt()}")
    
    # Test formatting
    test_emotions = [("радость", 5), ("тревога", 3), ("усталость", 2)]
    print(f"Formatted emotions: {format_emotion_list(test_emotions)}")
    
    # Test period names
    for days in [7, 14, 30, 90, 45]:
        print(f"{days} days -> {get_period_name(days)}")
    
    # Test settings formatting
    print(f"\nSettings text: {format_settings_text(True, 21)}")
    print(f"Settings text (disabled): {format_settings_text(False, 20)}")
