import requests
import telebot
import time
import threading

# Telegram Bot API ключ
TELEGRAM_BOT_TOKEN = '8166505294:AAGiQHrFRBYsOWNRIeH0IhxMUoJVq161xqw'
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# TON API ключ
TON_API_KEY = '14561e9d5cbc00dfc585cb33dc4fdca422ad45965398cd39651cef270f883305'
TON_API_URL = 'https://toncenter.com/api/v2/'

# Словарь: ключ — chat_id пользователя, значение — список отслеживаемых кошельков
user_wallets = {}

# Хранение последних обработанных транзакций
last_transactions = {}



CMC_API_KEY = 'ВАШ_API_КЛЮЧ'
CMC_API_URL = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest'

user_notifications = {}

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    if chat_id not in user_wallets:
        user_wallets[chat_id] = []  # Инициализируем пустой список кошельков для пользователя
    bot.reply_to(message, "Добро пожаловать! Используйте /addwallet и /removewallet для управления кошельками.")

# Обработчик команды /addwallet
# Функция для добавления кошелька
@bot.message_handler(commands=['addwallet'])
def add_wallet(message):
    chat_id = message.chat.id
    wallet = message.text.split(maxsplit=1)[-1].strip()
    if wallet:
        if wallet not in user_wallets[chat_id]:
            user_wallets[chat_id].append(wallet)
            # Инициализация списка обработанных транзакций
            transactions = get_wallet_transactions(wallet)
            if transactions:
                last_transactions[wallet] = [
                    tx.get('transaction_id', {}).get('hash') for tx in transactions
                ]
            else:
                last_transactions[wallet] = []
            bot.reply_to(message, f"Кошелек {wallet} добавлен для отслеживания.")
        else:
            bot.reply_to(message, "Кошелек уже добавлен в список отслеживания.")
    else:
        bot.reply_to(message, "Команда некорректна. Используйте /addwallet <адрес кошелька>.")


@bot.message_handler(commands=['notify'])
def add_notification(message):
    chat_id = message.chat.id
    try:
        # Разделяем сообщение на тикер, цену и пользовательский текст
        parts = message.text.split(maxsplit=3)
        if len(parts) < 3:
            bot.reply_to(message, "Некорректный формат. Используйте: /notify <тикер> <цена> <сообщение>")
            return

        ticker = parts[1].upper()
        price = float(parts[2])
        custom_message = parts[3] if len(parts) > 3 else f"Цена {ticker} достигла {price} USD!"

        # Инициализируем список уведомлений для пользователя
        if chat_id not in user_notifications:
            user_notifications[chat_id] = []
        
        # Добавляем уведомление
        user_notifications[chat_id].append((ticker, price, custom_message))
        bot.reply_to(message, f"Уведомление для {ticker} при цене {price} USD добавлено. Сообщение: {custom_message}")
    except ValueError:
        bot.reply_to(message, "Некорректный формат. Используйте: /notify <тикер> <цена> <сообщение>")


# Обработчик команды /removewallet
@bot.message_handler(commands=['removewallet'])
def remove_wallet(message):
    chat_id = message.chat.id
    wallet = message.text.split(maxsplit=1)[-1].strip()
    if wallet in user_wallets.get(chat_id, []):
        user_wallets[chat_id].remove(wallet)
        bot.reply_to(message, f"Кошелек {wallet} удален из списка отслеживания.")
    else:
        bot.reply_to(message, "Кошелек не найден в вашем списке отслеживания.")

# Обработчик команды /listwallets
@bot.message_handler(commands=['listwallets'])
def list_wallets(message):
    chat_id = message.chat.id
    wallets = user_wallets.get(chat_id, [])
    if wallets:
        wallets_list = "\n".join(wallets)
        bot.reply_to(message, f"Ваши отслеживаемые кошельки:\n{wallets_list}")
    else:
        bot.reply_to(message, "Ваш список отслеживаемых кошельков пуст.")

# Функции работы с транзакциями
def get_wallet_transactions(wallet):
    url = f"{TON_API_URL}getTransactions"
    params = {"address": wallet, "limit": 5, "api_key": TON_API_KEY}
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json().get('result', [])
    else:
        print(f"Ошибка API TON: {response.text}")
        return []


def get_crypto_price(ticker):
    """Получает текущую цену актива с помощью API CoinMarketCap."""
    API_KEY = "f3e2a0ef-1fae-4661-9ecd-2e4c0f08af35"
    url = f"https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    params = {"symbol": ticker, "convert": "USD"}
    headers = {"X-CMC_PRO_API_KEY": API_KEY}

    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        data = response.json()
        return data["data"][ticker]["quote"]["USD"]["price"]
    else:
        print(f"Ошибка API CoinMarketCap: {response.text}")
        return None


def analyze_transaction(transaction):
    """
    Анализ транзакции для определения типа операции и связанных токенов.
    Возвращает:
        - action (str): 'buy' или 'sell',
        - primary_token (str): основной токен (например, TON),
        - secondary_token (str или None): второй токен (например, NIKO), если есть.
    """
    in_msg = transaction.get('in_msg', {})
    out_msgs = transaction.get('out_msgs', [])
    action = None
    primary_token = None
    secondary_token = None

    # Проверяем входящие сообщения
    if in_msg:
        in_value = int(in_msg.get('value', 0))  # В нанотонах
        if in_value > 0:
            primary_token = 'TON'
            action = 'buy'

        # Проверяем, есть ли вторичный токен в поле jetton
        jetton_info = in_msg.get('jetton', {})
        if jetton_info:
            secondary_token = jetton_info.get('symbol', 'Unknown Token')

    # Проверяем исходящие сообщения
    for msg in out_msgs:
        out_value = int(msg.get('value', 0))  # В нанотонах
        if out_value > 0:
            primary_token = 'TON'
            action = 'sell'

        # Проверяем, есть ли вторичный токен в поле jetton
        jetton_info = msg.get('jetton', {})
        if jetton_info:
            secondary_token = jetton_info.get('symbol', 'Unknown Token')

    # Если оба токена определены, возвращаем их
    if primary_token and secondary_token:
        return action, primary_token, secondary_token
    elif primary_token:
        return action, primary_token, None
    else:
        return None, None, None

def check_wallets():
    """Проверка транзакций для всех кошельков, отслеживаемых пользователями"""
    for chat_id, wallets in user_wallets.items():
        for wallet in wallets:
            transactions = get_wallet_transactions(wallet)
            if not transactions:
                continue

            for transaction in transactions:
                tx_id = transaction.get('transaction_id', {}).get('hash')
                if tx_id and tx_id not in last_transactions.get(wallet, []):
                    action, token, second_token = analyze_transaction(transaction)
                    if action and token:
                        send_notification(chat_id, wallet, action, token, second_token, tx_id)
                    last_transactions.setdefault(wallet, []).append(tx_id)

def send_notification(chat_id, wallet, action, token, second_token, tx_id):
    """
    Отправка уведомлений пользователю с информацией о транзакции.
    """
    tx = f"https://tonviewer.com/transaction/{tx_id}"
    message = f"Кошелек: {wallet} {action} {token}. TX - {tx}"
    if second_token:
        message += f" в паре с {second_token}"  # Добавляем вторичный токен
    bot.send_message(chat_id=chat_id, text=message)

def check_notifications():
    """Проверяет цены и отправляет уведомления, если условия выполнены."""
    for chat_id, notifications in user_notifications.items():
        to_remove = []
        for ticker, target_price, custom_message in notifications:
            current_price = get_crypto_price(ticker)
            if current_price is not None and current_price >= target_price:
                # Вставляем текущую цену в сообщение
                notification_message = (
                    f"{custom_message}\n"
                    f"Текущая цена {ticker}: {current_price:.2f} USD."
                )
                bot.send_message(chat_id, notification_message)
                to_remove.append((ticker, target_price, custom_message))
        
        # Удаляем выполненные уведомления
        for item in to_remove:
            notifications.remove(item)

def wallet_monitor():
    """Функция для постоянной проверки транзакций"""
    while True:
        try:
            check_wallets()
        except Exception as e:
            print(f"Ошибка: {e}")
        time.sleep(60)


def notification_monitor():
    """Фоновая задача для проверки уведомлений."""
    while True:
        try:
            check_notifications()
        except Exception as e:
            print(f"Ошибка при проверке уведомлений: {e}")
        time.sleep(60)  # Проверяем раз в минуту

def start_bot():
    bot.polling()

if __name__ == "__main__":
    bot_thread = threading.Thread(target=start_bot)
    bot_thread.daemon = True  # Поток завершится при завершении программы
    bot_thread.start()

    monitor_thread = threading.Thread(target=wallet_monitor)
    monitor_thread.daemon = True
    monitor_thread.start()
    notification_thread = threading.Thread(target=notification_monitor)
    notification_thread.daemon = True
    notification_thread.start()


    bot_thread.join()
    monitor_thread.join()
