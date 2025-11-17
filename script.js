// Функция для авто-обновления сообщений
function startMessagePolling(chatId) {
    setInterval(async () => {
        try {
            const response = await fetch(`/api/get_messages/${chatId}`);
            if (response.ok) {
                const data = await response.json();
                updateMessagesUI(data.messages);
            }
        } catch (error) {
            console.error('Error polling messages:', error);
        }
    }, 3000);
}

// Обновление интерфейса сообщений
function updateMessagesUI(messages) {
    const container = document.getElementById('messagesContainer');
    if (container) {
        // Здесь можно добавить логику обновления без перезагрузки страницы
        console.log('New messages received:', messages);
    }
}

// Уведомления
function showNotification(title, message) {
    if ('Notification' in window && Notification.permission === 'granted') {
        new Notification(title, { body: message });
    }
}

// Запрос разрешения на уведомления
if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission();
}

// Обработка отправки форм
document.addEventListener('DOMContentLoaded', function() {
    // Авто-фокус на поле ввода сообщения
    const messageInput = document.getElementById('messageText');
    if (messageInput) {
        messageInput.focus();
    }
    
    // Подтверждение выхода
    const logoutLinks = document.querySelectorAll('a[href*="logout"]');
    logoutLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            if (!confirm('Вы уверены, что хотите выйти?')) {
                e.preventDefault();
            }
        });
    });
});

// Валидация номера телефона
function validatePhone(phone) {
    const phoneRegex = /^\+[0-9]{10,15}$/;
    return phoneRegex.test(phone);
}

// Валидация кода подтверждения
function validateCode(code) {
    return code.length === 5 && /^\d+$/.test(code);
}