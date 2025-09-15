#!/usr/bin/env python3
"""
Security and validation for EmoJournal Bot
Input validation and sanitization
"""

import re
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class InputValidator:
    """Валидация пользовательского ввода"""
    
    MAX_TEXT_LENGTH = 1000
    MAX_EMOTION_LENGTH = 100
    MAX_CAUSE_LENGTH = 500
    MAX_NOTE_LENGTH = 300
    
    # Простая проверка на подозрительный контент
    SUSPICIOUS_PATTERNS = [
        r'<script',
        r'javascript:',
        r'data:text/html',
        r'vbscript:',
        r'onload=',
        r'onerror=',
        r'eval\(',
        r'document\.cookie',
    ]
    
    # Запрещенные символы
    FORBIDDEN_CHARS = ['<', '>', '{', '}', '[', ']', '\\', '|']
    
    @classmethod
    def validate_text_input(cls, text: str, field_name: str = "text") -> Optional[str]:
        """Валидация текстового ввода"""
        if not text or not isinstance(text, str):
            return None
            
        text = text.strip()
        
        # Проверка на пустой текст
        if not text:
            return None
        
        # Проверка длины
        max_length = cls._get_max_length(field_name)
        if len(text) > max_length:
            logger.warning(f"Text too long for {field_name}: {len(text)} chars")
            text = text[:max_length]
        
        # Проверка на подозрительный контент
        text_lower = text.lower()
        for pattern in cls.SUSPICIOUS_PATTERNS:
            if re.search(pattern, text_lower):
                logger.warning(f"Suspicious content detected in {field_name}")
                return None
        
        # Удаление запрещенных символов
        for char in cls.FORBIDDEN_CHARS:
            if char in text:
                text = text.replace(char, '')
        
        # Удаление множественных пробелов
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text if text else None
    
    @classmethod
    def validate_emotion(cls, emotion: str) -> Optional[str]:
        """Специальная валидация для эмоций"""
        validated = cls.validate_text_input(emotion, "emotion")
        if not validated:
            return None
        
        # Эмоции должны быть короткими
        if len(validated) > cls.MAX_EMOTION_LENGTH:
            return None
        
        # Эмоции не должны содержать цифры
        if re.search(r'\d', validated):
            return None
        
        return validated.lower()
    
    @classmethod
    def validate_cause(cls, cause: str) -> Optional[str]:
        """Специальная валидация для причин"""
        return cls.validate_text_input(cause, "cause")
    
    @classmethod
    def validate_note(cls, note: str) -> Optional[str]:
        """Специальная валидация для заметок"""
        return cls.validate_text_input(note, "note")
    
    @classmethod
    def _get_max_length(cls, field_name: str) -> int:
        """Получить максимальную длину для поля"""
        limits = {
            'emotion': cls.MAX_EMOTION_LENGTH,
            'cause': cls.MAX_CAUSE_LENGTH,
            'note': cls.MAX_NOTE_LENGTH,
        }
        return limits.get(field_name, cls.MAX_TEXT_LENGTH)
    
    @classmethod
    def is_spam_like(cls, text: str) -> bool:
        """Проверка на спам-подобный контент"""
        if not text:
            return False
        
        # Много повторяющихся символов
        if re.search(r'(.)\1{10,}', text):
            return True
        
        # Много заглавных букв
        if len(text) > 10 and sum(1 for c in text if c.isupper()) / len(text) > 0.7:
            return True
        
        # Слишком много эмодзи
        emoji_count = len(re.findall(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]', text))
        if emoji_count > 5:
            return True
        
        return False


class ContentFilter:
    """Фильтрация контента"""
    
    # Список неприемлемых слов (базовый)
    INAPPROPRIATE_WORDS = [
        'spam', 'реклама', 'продам', 'куплю', 'заработок',
        'bitcoin', 'cryptocurrency', 'casino', 'казино'
    ]
    
    @classmethod
    def is_inappropriate(cls, text: str) -> bool:
        """Проверка на неприемлемый контент"""
        if not text:
            return False
        
        text_lower = text.lower()
        
        for word in cls.INAPPROPRIATE_WORDS:
            if word in text_lower:
                return True
        
        return False
    
    @classmethod
    def clean_text(cls, text: str) -> str:
        """Очистка текста от лишних символов"""
        if not text:
            return ""
        
        # Удаление множественных пробелов
        text = re.sub(r'\s+', ' ', text)
        
        # Удаление пробелов в начале и конце
        text = text.strip()
        
        # Удаление множественной пунктуации
        text = re.sub(r'[.]{3,}', '...', text)
        text = re.sub(r'[!]{2,}', '!', text)
        text = re.sub(r'[?]{2,}', '?', text)
        
        return text


def sanitize_user_input(text: str, input_type: str = "general") -> Optional[str]:
    """Главная функция для санитизации пользовательского ввода"""
    if not text:
        return None
    
    # Базовая валидация
    if input_type == "emotion":
        result = InputValidator.validate_emotion(text)
    elif input_type == "cause":
        result = InputValidator.validate_cause(text)
    elif input_type == "note":
        result = InputValidator.validate_note(text)
    else:
        result = InputValidator.validate_text_input(text)
    
    if not result:
        return None
    
    # Проверка на спам
    if InputValidator.is_spam_like(result):
        logger.warning(f"Spam-like content detected: {input_type}")
        return None
    
    # Проверка на неприемлемый контент
    if ContentFilter.is_inappropriate(result):
        logger.warning(f"Inappropriate content detected: {input_type}")
        return None
    
    # Финальная очистка
    result = ContentFilter.clean_text(result)
    
    return result if result else None


if __name__ == "__main__":
    # Тесты
    test_cases = [
        ("радость", "emotion", "радость"),
        ("ОЧЕНЬ ДОЛГИЙ ТЕКСТ" * 50, "emotion", None),
        ("<script>alert('hack')</script>", "general", None),
        ("работа стресс", "cause", "работа стресс"),
        ("!!!!!!!!!", "general", "!"),
        ("😀😀😀😀😀😀😀", "general", None),  # Много эмодзи
    ]
    
    for text, input_type, expected in test_cases:
        result = sanitize_user_input(text, input_type)
        status = "✓" if result == expected else "✗"
        print(f"{status} {input_type}: '{text}' -> '{result}'")
