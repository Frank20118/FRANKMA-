import os
import asyncio
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_session import Session
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
from telethon.tl.types import User
import json
from dotenv import load_dotenv
import logging
import hashlib

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['PERMANENT_SESSION_LIFETIME'] = 3600
Session(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

user_clients = {}

class TelegramWebClient:
    def __init__(self, session_name):
        self.api_id = int(os.getenv('API_ID'))
        self.api_hash = os.getenv('API_HASH')
        self.session_name = f"sessions/{session_name}"
        self.client = None
        self.is_authenticated = False
        
    async def connect(self):
        try:
            self.client = TelegramClient(self.session_name, self.api_id, self.api_hash)
            await self.client.connect()
            self.is_authenticated = await self.client.is_user_authorized()
            return self.is_authenticated
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False
    
    async def send_code_request(self, phone):
        try:
            if not self.client:
                await self.connect()
            return await self.client.send_code_request(phone)
        except Exception as e:
            logger.error(f"Code request error: {e}")
            raise e
    
    async def sign_in(self, phone, code, password=None):
        try:
            await self.client.sign_in(phone, code)
            self.is_authenticated = True
            return True
        except SessionPasswordNeededError:
            if password:
                await self.client.sign_in(password=password)
                self.is_authenticated = True
                return True
            return False
        except PhoneCodeInvalidError:
            return False
        except Exception as e:
            logger.error(f"Sign in error: {e}")
            return False
    
    async def get_dialogs(self):
        if not self.is_authenticated or not self.client:
            return []
        
        try:
            dialogs = await self.client.get_dialogs(limit=50)
            result = []
            
            for dialog in dialogs:
                chat_info = {
                    'id': dialog.id,
                    'name': dialog.name,
                    'unread_count': dialog.unread_count,
                    'is_user': isinstance(dialog.entity, User),
                    'is_group': hasattr(dialog.entity, 'megagroup') and dialog.entity.megagroup,
                    'is_channel': hasattr(dialog.entity, 'broadcast') and dialog.entity.broadcast,
                    'last_message': dialog.message.text[:100] + '...' if dialog.message and dialog.message.text else '📷 Медиа'
                }
                result.append(chat_info)
            
            return result
        except Exception as e:
            logger.error(f"Get dialogs error: {e}")
            return []
    
    async def get_messages(self, chat_id, limit=50):
        if not self.is_authenticated or not self.client:
            return []
        
        try:
            messages = await self.client.get_messages(chat_id, limit=limit)
            result = []
            
            for message in messages:
                if message:
                    message_info = {
                        'id': message.id,
                        'text': message.text or '📷 Медиа-сообщение',
                        'date': message.date.strftime('%H:%M %d.%m.%Y'),
                        'out': message.out,
                        'sender_id': message.sender_id
                    }
                    result.append(message_info)
            
            return result
        except Exception as e:
            logger.error(f"Get messages error: {e}")
            return []
    
    async def send_message(self, chat_id, text):
        if not self.is_authenticated or not self.client:
            return False
        
        try:
            await self.client.send_message(chat_id, text)
            return True
        except Exception as e:
            logger.error(f"Send message error: {e}")
            return False
    
    async def get_me(self):
        if not self.is_authenticated or not self.client:
            return None
        
        try:
            me = await self.client.get_me()
            return {
                'id': me.id,
                'first_name': me.first_name,
                'last_name': me.last_name,
                'username': me.username,
                'phone': me.phone
            }
        except Exception as e:
            logger.error(f"Get me error: {e}")
            return None

def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

@app.route('/')
def index():
    """Главная страница"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/home')
def home():
    """Альтернативный маршрут на главную"""
    return redirect(url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Страница входа"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        phone = request.form.get('phone')
        if not phone:
            return render_template('login.html', error='Введите номер телефона')
        
        session_id = f"user_{hashlib.md5(phone.encode()).hexdigest()}"
        
        try:
            client = TelegramWebClient(session_id)
            run_async(client.send_code_request(phone))
            session['phone'] = phone
            session['session_id'] = session_id
            user_clients[session_id] = client
            return render_template('login.html', step='code', phone=phone)
        
        except Exception as e:
            logger.error(f"Login error: {e}")
            return render_template('login.html', error=f'Ошибка: {str(e)}')
    
    return render_template('login.html', step='phone')

@app.route('/verify', methods=['POST'])
def verify():
    """Подтверждение входа с кодом"""
    if 'phone' not in session or 'session_id' not in session:
        return redirect(url_for('login'))
    
    code = request.form.get('code')
    password = request.form.get('password')
    phone = session['phone']
    session_id = session['session_id']
    
    if not code:
        return render_template('login.html', step='code', phone=phone, error='Введите код подтверждения')
    
    client = user_clients.get(session_id)
    if not client:
        return redirect(url_for('login'))
    
    try:
        success = run_async(client.sign_in(phone, code, password))
        if success:
            session['user_id'] = session_id
            session.permanent = True
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', step='code', phone=phone, error='Неверный код или пароль')
    
    except Exception as e:
        logger.error(f"Verify error: {e}")
        return render_template('login.html', step='code', phone=phone, error=f'Ошибка входа: {str(e)}')

@app.route('/dashboard')
def dashboard():
    """Панель управления"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    session_id = session['user_id']
    client = user_clients.get(session_id)
    
    if not client or not client.is_authenticated:
        return redirect(url_for('login'))
    
    try:
        user_info = run_async(client.get_me())
        dialogs = run_async(client.get_dialogs())
        
        if not user_info:
            return redirect(url_for('login'))
        
        return render_template('dashboard.html', user=user_info, dialogs=dialogs)
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return redirect(url_for('login'))

@app.route('/chat/<int:chat_id>')
def chat(chat_id):
    """Страница чата"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    session_id = session['user_id']
    client = user_clients.get(session_id)
    
    if not client:
        return redirect(url_for('login'))
    
    try:
        messages = run_async(client.get_messages(chat_id))
        dialogs = run_async(client.get_dialogs())
        current_chat = next((d for d in dialogs if d['id'] == chat_id), None)
        
        if not current_chat:
            return redirect(url_for('dashboard'))
        
        return render_template('chat.html', 
                             messages=messages, 
                             dialogs=dialogs, 
                             current_chat=current_chat,
                             chat_id=chat_id)
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return redirect(url_for('dashboard'))

@app.route('/api/send_message', methods=['POST'])
def api_send_message():
    """API для отправки сообщений"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    session_id = session['user_id']
    client = user_clients.get(session_id)
    
    if not client:
        return jsonify({'error': 'Client not found'}), 401
    
    data = request.json
    if not data:
        return jsonify({'error': 'No JSON data'}), 400
    
    chat_id = data.get('chat_id')
    text = data.get('text')
    
    if not chat_id or not text:
        return jsonify({'error': 'Missing parameters'}), 400
    
    success = run_async(client.send_message(chat_id, text))
    
    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Failed to send message'}), 500

@app.route('/api/get_messages/<int:chat_id>')
def api_get_messages(chat_id):
    """API для получения сообщений"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    session_id = session['user_id']
    client = user_clients.get(session_id)
    
    if not client:
        return jsonify({'error': 'Client not found'}), 401
    
    messages = run_async(client.get_messages(chat_id))
    return jsonify({'messages': messages})

@app.route('/logout')
def logout():
    """Выход из системы"""
    session_id = session.get('user_id')
    if session_id and session_id in user_clients:
        client = user_clients[session_id]
        if client and client.client:
            run_async(client.client.disconnect())
        del user_clients[session_id]
    
    session.clear()
    return redirect(url_for('index'))

@app.errorhandler(404)
def not_found(error):
    return render_template('error.html', error='Страница не найдена'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html', error='Внутренняя ошибка сервера'), 500

if __name__ == '__main__':
    os.makedirs('sessions', exist_ok=True)
    
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    logger.info(f"🚀 Starting Telegram Web Client on {host}:{port}")
    app.run(host=host, port=port, debug=debug)