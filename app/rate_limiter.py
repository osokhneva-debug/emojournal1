#!/usr/bin/env python3
"""
Rate limiting for EmoJournal Bot
Protection against spam and abuse
"""

import time
from collections import defaultdict
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)

class RateLimiter:
    """Ограничение частоты запросов"""
    
    def __init__(self, max_requests: int = 15, window_seconds: int = 60):
        """
        Инициализация rate limiter
        
        Args:
            max_requests: Максимальное количество запросов в окне
            window_seconds: Размер окна в секундах
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[int, List[float]] = defaultdict(list)
        self.last_cleanup = time.time()
        self.cleanup_interval = 300  # Очистка каждые 5 минут
    
    def is_allowed(self, user_id: int) -> bool:
        """
        Проверить, разрешен ли запрос для пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            True если запрос разрешен, False если превышен лимит
        """
        now = time.time()
        
        # Периодическая очистка старых записей
        self._cleanup_if_needed(now)
        
        user_requests = self.requests[user_id]
        
        # Удалить старые запросы вне окна
        cutoff_time = now - self.window_seconds
        self.requests[user_id] = [req_time for req_time in user_requests 
                                  if req_time > cutoff_time]
        
        # Проверить лимит
        if len(self.requests[user_id]) >= self.max_requests:
            logger.warning(f"Rate limit exceeded for user {user_id}: "
                          f"{len(self.requests[user_id])} requests in {self.window_seconds}s")
            return False
        
        # Добавить текущий запрос
        self.requests[user_id].append(now)
        return True
    
    def get_remaining_requests(self, user_id: int) -> int:
        """Получить количество оставшихся запросов"""
        now = time.time()
        cutoff_time = now - self.window_seconds
        
        user_requests = self.requests.get(user_id, [])
        current_count = len([req for req in user_requests if req > cutoff_time])
        
        return max(0, self.max_requests - current_count)
    
    def get_reset_time(self, user_id: int) -> float:
        """Получить время до сброса лимита"""
        user_requests = self.requests.get(user_id, [])
        if not user_requests:
            return 0
        
        oldest_request = min(user_requests)
        reset_time = oldest_request + self.window_seconds
        
        return max(0, reset_time - time.time())
    
    def _cleanup_if_needed(self, now: float):
        """Периодическая очистка устаревших записей"""
        if now - self.last_cleanup < self.cleanup_interval:
            return
        
        cutoff_time = now - self.window_seconds * 2  # Удаляем записи старше 2 окон
        
        # Очистить устаревшие записи
        users_to_remove = []
        for user_id, requests in self.requests.items():
            self.requests[user_id] = [req for req in requests if req > cutoff_time]
            
            # Если у пользователя нет активных запросов, удалить его
            if not self.requests[user_id]:
                users_to_remove.append(user_id)
        
        for user_id in users_to_remove:
            del self.requests[user_id]
        
        self.last_cleanup = now
        
        if users_to_remove:
            logger.info(f"Cleaned up rate limiter data for {len(users_to_remove)} users")


class CommandRateLimiter:
    """Специальный rate limiter для команд"""
    
    def __init__(self):
        """Разные лимиты для разных типов команд"""
        self.limiters = {
            'fast': RateLimiter(max_requests=30, window_seconds=60),    # /note, /help
            'medium': RateLimiter(max_requests=10, window_seconds=60),  # /summary, /export
            'slow': RateLimiter(max_requests=3, window_seconds=300),    # /delete_me
            'admin': RateLimiter(max_requests=5, window_seconds=60),    # /stats
        }
    
    def is_allowed(self, user_id: int, command_type: str = 'fast') -> bool:
        """
        Проверить лимит для конкретного типа команды
        
        Args:
            user_id: ID пользователя
            command_type: Тип команды ('fast', 'medium', 'slow', 'admin')
        """
        limiter = self.limiters.get(command_type, self.limiters['fast'])
        return limiter.is_allowed(user_id)
    
    def get_command_type(self, command: str) -> str:
        """Определить тип команды по её названию"""
        command_types = {
            'fast': ['start', 'help', 'note', 'pause', 'resume'],
            'medium': ['summary', 'export', 'timezone'],
            'slow': ['delete_me'],
            'admin': ['stats'],
        }
        
        command = command.lstrip('/')
        
        for cmd_type, commands in command_types.items():
            if command in commands:
                return cmd_type
        
        return 'fast'  # По умолчанию


class AntiSpamFilter:
    """Фильтр против спама"""
    
    def __init__(self):
        self.recent_messages: Dict[int, List[str]] = defaultdict(list)
        self.message_history_limit = 5
        self.similarity_threshold = 0.8
    
    def is_spam(self, user_id: int, message: str) -> bool:
        """
        Проверить, является ли сообщение спамом
        
        Args:
            user_id: ID пользователя
            message: Текст сообщения
            
        Returns:
            True если сообщение похоже на спам
        """
        if not message:
            return False
        
        message = message.lower().strip()
        user_messages = self.recent_messages[user_id]
        
        # Проверить на повторяющиеся сообщения
        similar_count = 0
        for prev_msg in user_messages:
            if self._calculate_similarity(message, prev_msg) > self.similarity_threshold:
                similar_count += 1
        
        # Если слишком много похожих сообщений - это спам
        is_spam = similar_count >= 3
        
        if is_spam:
            logger.warning(f"Spam detected for user {user_id}: similar message count {similar_count}")
        
        # Добавить сообщение в историю
        user_messages.append(message)
        if len(user_messages) > self.message_history_limit:
            user_messages.pop(0)
        
        return is_spam
    
    def _calculate_similarity(self, msg1: str, msg2: str) -> float:
        """Простой расчет схожести строк"""
        if not msg1 or not msg2:
            return 0.0
        
        # Простая метрика: количество общих слов
        words1 = set(msg1.split())
        words2 = set(msg2.split())
        
        if not words1 and not words2:
            return 1.0
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0.0


class GlobalRateLimiter:
    """Глобальный rate limiter для всего бота"""
    
    def __init__(self, max_requests_per_second: int = 30):
        """
        Args:
            max_requests_per_second: Максимальное количество запросов в секунду для всего бота
        """
        self.max_rps = max_requests_per_second
        self.requests = []
    
    def is_allowed(self) -> bool:
        """Проверить глобальный лимит"""
        now = time.time()
        
        # Удалить запросы старше 1 секунды
        self.requests = [req_time for req_time in self.requests if req_time > now - 1.0]
        
        # Проверить лимит
        if len(self.requests) >= self.max_rps:
            logger.warning(f"Global rate limit exceeded: {len(self.requests)} requests per second")
            return False
        
        # Добавить текущий запрос
        self.requests.append(now)
        return True


# Глобальные экземпляры
user_rate_limiter = RateLimiter(max_requests=20, window_seconds=60)
command_rate_limiter = CommandRateLimiter()
anti_spam_filter = AntiSpamFilter()
global_rate_limiter = GlobalRateLimiter(max_requests_per_second=25)


def check_user_limits(user_id: int, message: str = "", command: str = "") -> tuple[bool, str]:
    """
    Комплексная проверка всех лимитов для пользователя
    
    Args:
        user_id: ID пользователя
        message: Текст сообщения (опционально)
        command: Команда (опционально)
        
    Returns:
        (allowed: bool, reason: str)
    """
    # Проверить глобальный лимит
    if not global_rate_limiter.is_allowed():
        return False, "Сервер перегружен. Попробуйте через несколько секунд."
    
    # Проверить пользовательский лимит
    if not user_rate_limiter.is_allowed(user_id):
        reset_time = int(user_rate_limiter.get_reset_time(user_id))
        return False, f"Слишком много запросов. Попробуйте через {reset_time} секунд."
    
    # Проверить лимит команд
    if command:
        command_type = command_rate_limiter.get_command_type(command)
        if not command_rate_limiter.is_allowed(user_id, command_type):
            return False, f"Слишком часто используете команду /{command}. Подождите немного."
    
    # Проверить на спам
    if message and anti_spam_filter.is_spam(user_id, message):
        return False, "Обнаружено повторяющееся сообщение. Пожалуйста, пишите разнообразнее."
    
    return True, ""


if __name__ == "__main__":
    # Тесты
    limiter = RateLimiter(max_requests=3, window_seconds=10)
    
    print("Testing rate limiter...")
    
    # Тест нормального использования
    for i in range(3):
        result = limiter.is_allowed(123)
        print(f"Request {i+1}: {'✓' if result else '✗'}")
    
    # Этот запрос должен быть отклонен
    result = limiter.is_allowed(123)
    print(f"Request 4 (should fail): {'✓' if result else '✗'}")
    
    # Тест другого пользователя
    result = limiter.is_allowed(456)
    print(f"Different user: {'✓' if result else '✗'}")
    
    print("Rate limiter tests completed!")
