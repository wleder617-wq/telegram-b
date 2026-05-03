import os
import sqlite3
import secrets as _secrets
import time
import threading
import traceback
 
import requests
import telebot
from telebot import types
 
BOT_TOKEN = os.environ.get(
    "PAYMENT_BOT_TOKEN",
    "8638636800:AAE8HebDVlk5N28kxiWIgKZdaWSWRdVQHqk",
)
MAIN_BOT_USERNAME = os.environ.get("MAIN_BOT_USERNAME", "freevidosii_bot")
# Payment bot self-username (for logs/reference)
PAYMENT_BOT_USERNAME = os.environ.get("PAYMENT_BOT_USERNAME", "shyareeet_bot")
MAIN_API_URL = os.environ.get("MAIN_API_URL", "http://127.0.0.1:5000/api/v2/deliver")
DELIVERY_API_SECRET = os.environ.get(
    "DELIVERY_API_SECRET", "v2_delivery_api_shared_secret_2024"
)
DATABASE = os.environ.get("PAYMENTS_DB", "/home/ubuntu/runbot/payments.db")
 
# product_key -> (stars_price, video_count)
PRODUCTS = {
    "buy_5": (5, 5),
    "buy_50": (50, 50),
    "buy_111": (100, 111),
    "buy_120": (100, 120),
    "buy_350": (250, 350),
    "buy_750": (500, 750),
    "buy_1600": (1000, 1600),
}
 
PRODUCT_LABELS = {
    "buy_5": "⭐ 7 Stars = 7 Videos",
    "buy_50": "⭐ 65 Stars = 65 Videos",
    "buy_111": "⭐ 100 Stars ➔ 111 Videos",
    "buy_120": "⭐ 100 Stars ➔ 120 Videos",
    "buy_350": "⭐ 250 Stars ➔ 350 Videos",
    "buy_750": "⭐ 500 Stars ➔ 750 Videos",
    "buy_1600": "⭐ 1000 Stars ➔ 1600 Videos",
}
 
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
 
 
def _ensure_table():
    with sqlite3.connect(DATABASE) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS pending_deliveries (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                video_count INTEGER NOT NULL,
                stars_paid INTEGER NOT NULL,
                payment_charge_id TEXT,
                created_at INTEGER NOT NULL,
                delivered_at INTEGER,
                delivered INTEGER DEFAULT 0
            )"""
        )
        conn.commit()
 
 
@bot.message_handler(commands=["start"])
def handle_start(message):
    user_id = message.from_user.id
    args = message.text.split()
 
    # No product specified: show explainer
    if len(args) < 2 or args[1] not in PRODUCTS:
        kb = types.InlineKeyboardMarkup()
        kb.add(
            types.InlineKeyboardButton(
                "🎬 Go to main bot", url=f"https://t.me/{MAIN_BOT_USERNAME}"
            )
        )
        bot.send_message(
            message.chat.id,
            (
                "💳 <b>Payment Bot</b>\n"
                "━━━━━━━━━━━━━━━━\n\n"
                "This bot only processes <b>Stars payments</b>.\n"
                f"Please open @{MAIN_BOT_USERNAME} to browse content and choose a package.\n\n"
                "After you pick a package there, you will be redirected back here "
                "with the correct invoice automatically."
            ),
            reply_markup=kb,
        )
        return
 
    product = args[1]
    stars, count = PRODUCTS[product]
    label = PRODUCT_LABELS.get(product, f"{count} Videos")
 
    prices = [types.LabeledPrice(label=f"{count} Premium Videos", amount=stars)]
    bot.send_invoice(
        message.chat.id,
        title=f"Premium Video Pack ({count})",
        description=(
            f"{label}\n\nGet {count} premium videos delivered "
            f"directly in @{MAIN_BOT_USERNAME}."
        ),
        invoice_payload=f"pkg|{product}|{user_id}",
        provider_token="",  # Stars: empty provider token
        currency="XTR",
        prices=prices,
        start_parameter="premium_videos",
    )
 
 
@bot.pre_checkout_query_handler(func=lambda q: True)
def on_checkout(q):
    try:
        bot.answer_pre_checkout_query(q.id, ok=True)
    except Exception as exc:
        print(f"pre_checkout failed: {exc}")
 
 
def _notify_main_bot_async(payload):
    def _send():
        try:
            r = requests.post(MAIN_API_URL, json=payload, timeout=10)
            print(f"Main bot notified: status={r.status_code} body={r.text[:200]}")
        except Exception as exc:
            print(f"Failed to notify main bot: {exc}")
 
    threading.Thread(target=_send, daemon=True).start()
 
 
@bot.message_handler(content_types=["successful_payment"])
def on_payment(message):
    try:
        sp = message.successful_payment
        user_id = message.from_user.id
        payload = sp.invoice_payload or ""
        parts = payload.split("|")
        if len(parts) != 3 or parts[0] != "pkg":
            bot.send_message(message.chat.id, "⚠️ Invalid payment payload.")
            return
        product = parts[1]
        if product not in PRODUCTS:
            bot.send_message(message.chat.id, "⚠️ Unknown product.")
            return
 
        stars, count = PRODUCTS[product]
        token = _secrets.token_hex(16)
        now = int(time.time())
 
        try:
            with sqlite3.connect(DATABASE) as conn:
                conn.execute(
                    "INSERT INTO pending_deliveries "
                    "(token, user_id, video_count, stars_paid, payment_charge_id, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        token,
                        user_id,
                        count,
                        sp.total_amount,
                        sp.telegram_payment_charge_id,
                        now,
                    ),
                )
                conn.commit()
        except Exception as exc:
            print(f"pending_deliveries insert failed: {exc}")
 
        _notify_main_bot_async({
            "secret": DELIVERY_API_SECRET,
            "token": token,
            "user_id": user_id,
            "count": count,
            "stars": sp.total_amount,
            "charge_id": sp.telegram_payment_charge_id,
        })
 
        deep_link = f"https://t.me/{MAIN_BOT_USERNAME}?start=deliver_{token}"
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🎬 Get your videos →", url=deep_link))
        bot.send_message(
            message.chat.id,
            (
                "✅ <b>Payment Successful!</b>\n"
                "━━━━━━━━━━━━━━━━\n"
                f"💰 Amount: {sp.total_amount} ⭐\n"
                f"📦 Package: <b>{count} Premium Videos</b>\n\n"
                f"Your videos are being sent in @{MAIN_BOT_USERNAME} right now.\n"
                "Tap below to open the main bot."
            ),
            reply_markup=kb,
        )
    except Exception:
        traceback.print_exc()
        try:
            bot.send_message(
                message.chat.id,
                "⚠️ Something went wrong recording your payment. "
                f"Please contact support with ID <code>{message.from_user.id}</code>.",
            )
        except Exception:
            pass
 
 
@bot.message_handler(func=lambda m: True)
def catch_all(message):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton(
            "🎬 Open main bot", url=f"https://t.me/{MAIN_BOT_USERNAME}"
        )
    )
    bot.send_message(
        message.chat.id,
        (
            f"This bot only handles payments. Please use @{MAIN_BOT_USERNAME} "
            "for everything else."
        ),
        reply_markup=kb,
    )
 
 
if __name__ == "__main__":
    _ensure_table()
    print(f"Payment bot starting (username=@{MAIN_BOT_USERNAME} for handoff)...")
    bot.infinity_polling(timeout=30, long_polling_timeout=30)
 
