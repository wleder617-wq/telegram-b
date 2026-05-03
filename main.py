import telebot
from telebot import types
import sqlite3
import os
import time
from flask import Flask
from threading import Thread

from premium_emojis import get_emoji_tag
from i18n import get_string, PREMIUM_EMOJI_LINE

E_HAND = get_emoji_tag('WAVE', '👋')
E_HEART = get_emoji_tag('HEART_RED', '❤️')
E_STAR = get_emoji_tag('STAR_GOLD', '⭐')
E_WOW = get_emoji_tag('WOW_FACE', '😮')
E_FIRE = get_emoji_tag('FIRE', '🔥')
E_GIFT = get_emoji_tag('GIFT', '🎁')
E_CHECK = get_emoji_tag('CHECK_MARK', '✅')
E_CHECK_ALT = get_emoji_tag('CHECK_MARK_ALT', '✔️')
E_PLANE = get_emoji_tag('PLANE', '✈️')
E_WINK = get_emoji_tag('WINK', '😉')
E_KISS = get_emoji_tag('KISS', '😘')
E_PLEASE = get_emoji_tag('PLEADING_FACE', '🥺')
E_SPARKLES = get_emoji_tag('STAR_GOLD', '✨')

TOKEN = "8721285488AAGym7ilHiXEBHQ-gkjIsTtNzfdZFwSZsrw"
DATABASE = 'payments.db'
PROVIDER_TOKEN = '187703658:TEST:5d5b04968f5d1a03e9fc853d6895cf8f8f5254fb'
ADMIN_IDS = [7972155518]
NOTIFY_IDS = [7972155518]

REFERRAL_TIERS = [
    (2, 5, "Bronze"),
    (5, 12, "Silver"),
    (10, 25, "Gold"),
    (25, 62, "Platinum"),
    (50, 125, "Diamond"),
    (100, 250, "Legend"),
    (200, 500, "Ultimate"),
    (250, 750, "Supreme"),
]

def is_admin(user_id):
    return user_id in ADMIN_IDS

bot = telebot.TeleBot(TOKEN)
BOT_USERNAME = None
app = Flask(__name__)

def setup_bot_commands():
    commands = [
        types.BotCommand("start", "Start Bot"),
        types.BotCommand("offer", "Special Offers")
    ]
    try:
        bot.set_my_commands(commands)
    except Exception as e:
        print(f"Error setting commands: {e}")

setup_bot_commands()

@app.route('/')
def home():
    return "Bot is running!", 200

@app.route('/health')
def health():
    return "OK", 200

def run_flask():
    app.run(host='0.0.0.0', port=5000)

def init_db():
    print(f"DEBUG: Initializing database at {os.path.abspath(DATABASE)}")
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, language TEXT DEFAULT 'en', last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS payments (user_id INTEGER, payment_id TEXT, amount INTEGER, currency TEXT, PRIMARY KEY (user_id, payment_id))''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS videos (id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT NOT NULL, file_name TEXT, file_size INTEGER, duration INTEGER, added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS sent_videos (user_id INTEGER, video_id INTEGER, PRIMARY KEY (user_id, video_id))''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS referrals (referrer_id INTEGER, referred_id INTEGER, PRIMARY KEY (referred_id))''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS share_rewards (user_id INTEGER PRIMARY KEY, rewarded BOOLEAN DEFAULT FALSE)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS banned_users (user_id INTEGER PRIMARY KEY, banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS gift_claims (user_id INTEGER PRIMARY KEY, last_claim_time TIMESTAMP NOT NULL)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS daily_subscriptions (user_id INTEGER PRIMARY KEY, days_remaining INTEGER, last_sent_date TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS processed_deep_links (link_id TEXT PRIMARY KEY, used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS milestones (user_id INTEGER PRIMARY KEY, total_spent INTEGER DEFAULT 0, rewarded BOOLEAN DEFAULT FALSE)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS admin_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER, action TEXT, target_id INTEGER, details TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS referral_rewards (user_id INTEGER, tier_invites INTEGER, claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (user_id, tier_invites))''')
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)''')
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_sent_videos_user ON sent_videos(user_id)''')
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_videos_file_id ON videos(file_id)''')
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id)''')
        try:
            cursor.execute('ALTER TABLE users ADD COLUMN language TEXT')
        except sqlite3.OperationalError:
            pass
        conn.commit()

def is_banned(user_id):
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM banned_users WHERE user_id = ?', (user_id,))
        return cursor.fetchone() is not None

def ban_user(user_id):
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT OR IGNORE INTO banned_users (user_id) VALUES (?)', (user_id,))
        conn.commit()

def unban_user(user_id):
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM banned_users WHERE user_id = ?', (user_id,))
        conn.commit()

def mark_link_used(link_id):
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT INTO processed_deep_links (link_id) VALUES (?)', (link_id,))
            conn.commit()
            return True
    except sqlite3.IntegrityError:
        return False

ADMIN_STATES = {}

def save_user(user_id, username):
    is_new = False
    with sqlite3.connect(DATABASE, isolation_level=None) as conn:
        cursor = conn.cursor()
        cursor.execute('BEGIN TRANSACTION')
        try:
            cursor.execute('SELECT 1 FROM users WHERE user_id = ?', (user_id,))
            if not cursor.fetchone():
                is_new = True
                cursor.execute('INSERT INTO users (user_id, username, last_seen) VALUES (?, ?, CURRENT_TIMESTAMP)', (user_id, username))
            else:
                cursor.execute('UPDATE users SET username = ?, last_seen = CURRENT_TIMESTAMP WHERE user_id = ?', (username, user_id))
            cursor.execute('COMMIT')
        except Exception as e:
            cursor.execute('ROLLBACK')
            print(f"Error saving user: {e}")
    if is_new:
        for admin_id in NOTIFY_IDS:
            try:
                bot.send_message(admin_id,
                    f"{E_HEART} <b>New Member Joined!</b>\n\n"
                    f"\U0001f464 <b>User:</b> @{escape_html(username) if username else 'N/A'}\n"
                    f"\U0001f194 <b>ID:</b> <code>{user_id}</code>\n"
                    f"\u2728 <b>Welcome them to the club!</b>",
                    parse_mode='HTML')
            except: pass

def escape_html(text):
    if not text: return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def add_referral(referrer_id, referred_id):
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM referrals WHERE referred_id = ?', (referred_id,))
        if cursor.fetchone(): return False
        cursor.execute('INSERT OR IGNORE INTO referrals (referrer_id, referred_id) VALUES (?, ?)', (referrer_id, referred_id))
        conn.commit()
        return True

def get_referral_count(referrer_id):
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM referrals WHERE referrer_id = ?', (referrer_id,))
        return cursor.fetchone()[0]

def get_claimed_tiers(user_id):
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT tier_invites FROM referral_rewards WHERE user_id = ?', (user_id,))
        return [row[0] for row in cursor.fetchall()]

def claim_tier(user_id, tier_invites):
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT INTO referral_rewards (user_id, tier_invites) VALUES (?, ?)', (user_id, tier_invites))
            conn.commit()
            return True
    except sqlite3.IntegrityError:
        return False

def get_next_tier(ref_count, claimed_tiers):
    for invites_needed, reward, name in REFERRAL_TIERS:
        if invites_needed not in claimed_tiers:
            return (invites_needed, reward, name)
    return None

def get_referral_leaderboard(limit=10):
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT r.referrer_id, u.username, COUNT(*) as ref_count
            FROM referrals r
            LEFT JOIN users u ON r.referrer_id = u.user_id
            GROUP BY r.referrer_id
            ORDER BY ref_count DESC
            LIMIT ?
        ''', (limit,))
        return cursor.fetchall()

def save_video(file_id, file_name=None, file_size=None, duration=None):
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM videos WHERE file_id = ?', (file_id,))
            exists = cursor.fetchone()
            if exists:
                return exists[0]
            cursor.execute('INSERT INTO videos (file_id, file_name, file_size, duration) VALUES (?, ?, ?, ?)', (file_id, file_name, file_size, duration))
            conn.commit()
            return cursor.lastrowid
    except Exception as e:
        print(f"DB error save_video: {e}")
        return None

def get_unsent_videos(user_id, limit=50):
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))

            # First try to get truly unsent videos
            query_unsent = '''
                SELECT v.id, v.file_id 
                FROM videos v 
                LEFT JOIN sent_videos sv ON v.id = sv.video_id AND sv.user_id = ? 
                WHERE sv.video_id IS NULL 
                ORDER BY RANDOM() 
                LIMIT ?
            '''
            cursor.execute(query_unsent, (user_id, limit))
            videos = cursor.fetchall()

            # If we don't have enough unsent videos, fill the rest with random videos (recycling)
            if len(videos) < limit:
                needed = limit - len(videos)
                exclude_ids = [v[0] for v in videos]
                placeholders = ','.join(['?'] * len(exclude_ids))

                query_recycle = f'''
                    SELECT id, file_id 
                    FROM videos 
                    {f"WHERE id NOT IN ({placeholders})" if exclude_ids else ""}
                    ORDER BY RANDOM() 
                    LIMIT ?
                '''
                params = exclude_ids + [needed]
                cursor.execute(query_recycle, params)
                videos.extend(cursor.fetchall())

            return videos[:limit]
    except Exception as e:
        print(f"DB error get_unsent_videos: {e}")
        return []

def save_sent_video(user_id, video_id):
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT OR IGNORE INTO sent_videos (user_id, video_id) VALUES (?, ?)', (user_id, video_id))
            conn.commit()
    except Exception as e:
        print(f"DB error save_sent_video: {e}")

import queue
import threading
from concurrent.futures import ThreadPoolExecutor

delivery_queue = queue.Queue()
delivery_pool = ThreadPoolExecutor(max_workers=10)

def process_delivery(task):
    try:
        if len(task) == 5:
            user_id, video_list, success_callback, failure_callback, admin_msg_id = task
        else:
            user_id, video_list, success_callback, failure_callback = task
            admin_msg_id = None

        total_vids = len(video_list)
        CAPTION = ""
        success_count = 0

        for idx, (v_id, f_id) in enumerate(video_list):
            try:
                time.sleep(0.3)
                bot.send_video(user_id, f_id, caption=CAPTION)
                save_sent_video(user_id, v_id)
                success_count += 1

                if admin_msg_id and (success_count % 5 == 0 or success_count == total_vids):
                    for admin_id in NOTIFY_IDS:
                        try:
                            bot.edit_message_text(
                                f"\U0001f680 <b>Delivery Progress</b>\n"
                                f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
                                f"User ID: <code>{user_id}</code>\n"
                                f"Progress: <b>{success_count}/{total_vids}</b> videos\n"
                                f"Status: <b>Sending...</b>",
                                admin_id, admin_msg_id, parse_mode='HTML'
                            )
                        except: pass
            except Exception as e:
                print(f"Worker error: {e}")
                if "blocked" in str(e).lower(): break

        if admin_msg_id:
            for admin_id in NOTIFY_IDS:
                try:
                    bot.edit_message_text(
                        f"\u2705 <b>Delivery Complete</b>\n"
                        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
                        f"User ID: <code>{user_id}</code>\n"
                        f"Total: <b>{success_count}/{total_vids}</b> videos sent.",
                        admin_id, admin_msg_id, parse_mode='HTML'
                    )
                except: pass

        if success_count > 0:
            if success_callback: success_callback(user_id, success_count)
        else:
            if failure_callback: failure_callback(user_id)
    except Exception as e:
        print(f"Delivery worker error: {e}")

def delivery_dispatcher():
    while True:
        try:
            task = delivery_queue.get()
            delivery_pool.submit(process_delivery, task)
            delivery_queue.task_done()
        except Exception as e:
            print(f"Dispatcher error: {e}")

threading.Thread(target=delivery_dispatcher, daemon=True).start()

def get_user_language(user_id):
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT language FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        return row[0] if row and row[0] else 'en'

def set_user_language(user_id, lang):
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET language = ? WHERE user_id = ?', (lang, user_id))
        conn.commit()

def language_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("English 🇺🇸", callback_data="set_lang_en"),
        types.InlineKeyboardButton("Русский 🇷🇺", callback_data="set_lang_ru"),
        types.InlineKeyboardButton("हिन्दी 🇮🇳", callback_data="set_lang_hi"),
        types.InlineKeyboardButton("Español 🇪🇸", callback_data="set_lang_es"),
        types.InlineKeyboardButton("Deutsch 🇩🇪", callback_data="set_lang_de"),
        types.InlineKeyboardButton("Português 🇵🇹", callback_data="set_lang_pt")
    )
    return keyboard

@bot.callback_query_handler(func=lambda call: call.data.startswith("set_lang_"))
def handle_set_lang(call):
    lang = call.data.replace("set_lang_", "")
    set_user_language(call.from_user.id, lang)
    bot.answer_callback_query(call.id, f"Language set to {lang}!")
    handle_back_to_start(call)

def notify_delivery_success(user_id, count):
    lang = get_user_language(user_id)
    try:
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(styled_button(get_string('referral_menu', lang), callback_data="referral_menu", style="success"))
        keyboard.add(styled_button(get_string('back_to_start', lang), callback_data="back_to_start", style="primary"))

        bot.send_message(user_id, get_string('delivery_success', lang, count=count), parse_mode='HTML', reply_markup=keyboard)
    except: pass

def notify_delivery_failure(user_id):
    lang = get_user_language(user_id)
    try: bot.send_message(user_id, get_string('delivery_failed', lang, user_id=user_id), parse_mode='HTML')
    except: pass

def get_total_users():
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM users')
            return cursor.fetchone()[0]
    except:
        return 0

def styled_button(text, callback_data=None, url=None, style="primary", emoji_id=None):
    btn = types.InlineKeyboardButton(text=text, callback_data=callback_data, url=url)
    original_to_dict = btn.to_dict
    def to_dict():
        data = original_to_dict()
        data['style'] = style
        if emoji_id:
            data['icon_custom_emoji_id'] = emoji_id
        return data
    btn.to_dict = to_dict
    return btn

def get_user_milestone(user_id):
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT total_spent, rewarded FROM milestones WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        if row: return row
        return (0, False)

def update_user_milestone(user_id, amount):
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO milestones (user_id, total_spent) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET total_spent = total_spent + EXCLUDED.total_spent
        ''', (user_id, amount))
        conn.commit()
        cursor.execute('SELECT total_spent, rewarded FROM milestones WHERE user_id = ?', (user_id,))
        total, rewarded = cursor.fetchone()
        if total >= 750 and not rewarded:
            cursor.execute('UPDATE milestones SET rewarded = TRUE WHERE user_id = ?', (user_id,))
            conn.commit()
            return True
    return False

def log_admin_action(admin_id, action, target_id=None, details=None):
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT INTO admin_logs (admin_id, action, target_id, details) VALUES (?, ?, ?, ?)',
                         (admin_id, action, target_id, details))
            conn.commit()
    except Exception as e:
        print(f"Error logging admin action: {e}")

def build_referral_progress(ref_count, claimed_tiers):
    lines = []
    for invites_needed, reward, name in REFERRAL_TIERS:
        if invites_needed in claimed_tiers:
            lines.append(f"\u2705 <b>{name}</b> \u2502 {invites_needed} invites \u2502 {reward} videos \u2502 <b>CLAIMED</b>")
        elif ref_count >= invites_needed:
            lines.append(f"\U0001f381 <b>{name}</b> \u2502 {invites_needed} invites \u2502 {reward} videos \u2502 <b>READY!</b>")
        else:
            lines.append(f"\U0001f512 <b>{name}</b> \u2502 {invites_needed} invites \u2502 {reward} videos \u2502 {ref_count}/{invites_needed}")
    return "\n".join(lines)

def start_keyboard(user_id=None):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    lang = get_user_language(user_id) if user_id else 'en'

    # Get Star Emoji ID
    from premium_emojis import PREMIUM_EMOJIS
    star_emoji_id = PREMIUM_EMOJIS.get('STAR_GOLD')

    keyboard.add(
        styled_button(text=get_string('buy_5', lang), callback_data="buy_5", style="primary", emoji_id=star_emoji_id),
        styled_button(text=get_string('buy_50', lang), callback_data="buy_50", style="primary", emoji_id=star_emoji_id)
    )

    if user_id:
        ref_count = get_referral_count(user_id)
        claimed_tiers = get_claimed_tiers(user_id)
        next_tier = get_next_tier(ref_count, claimed_tiers)

        global BOT_USERNAME
        if not BOT_USERNAME: BOT_USERNAME = bot.get_me().username
        invite_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        share_text = f"Hey! I found an amazing Video Bot! 🎬\n\nGet videos just by joining!\nInvite friends & unlock videos!\nContent delivered instantly!\n\nJoin now\n{invite_link}"
        import urllib.parse
        share_url = f"https://t.me/share/url?url={urllib.parse.quote(invite_link)}&text={urllib.parse.quote(share_text)}"

        has_claimable = any(
            ref_count >= inv and inv not in claimed_tiers
            for inv, _, _ in REFERRAL_TIERS
        )
        if has_claimable:
            keyboard.add(styled_button(
                text=get_string('claim_rewards', lang),
                callback_data="claim_rewards", style="danger", emoji_id=PREMIUM_EMOJIS.get('GIFT')))

        if next_tier:
            invites_needed, reward, name = next_tier
            keyboard.add(styled_button(
                text=f"{get_string('invite_friends', lang)} ({ref_count}/{invites_needed})",
                url=share_url, style="success", emoji_id=PREMIUM_EMOJIS.get('WAVE')))
        else:
            keyboard.add(styled_button(
                text=f"{get_string('all_tiers_done', lang)} ({ref_count})",
                url=share_url, style="success", emoji_id=PREMIUM_EMOJIS.get('STAR_GOLD')))

        keyboard.add(styled_button(
        text=get_string('referral_menu', lang) + f" ({ref_count})",
        callback_data="referral_menu", style="primary", emoji_id=PREMIUM_EMOJIS.get('HEART_RED')))

    hot_emoji_1 = "6087135901694040510"
    hot_emoji_2 = "6087135936053777739"
    hot_btn = types.InlineKeyboardButton(text="⭐⭐ Offers", callback_data="offer_menu")
    original_hot_to_dict = hot_btn.to_dict
    def hot_to_dict():
        data = original_hot_to_dict()
        data['style'] = 'success'
        data['entities'] = [
            {"type": "custom_emoji", "offset": 0, "length": 1, "custom_emoji_id": hot_emoji_1},
            {"type": "custom_emoji", "offset": 1, "length": 1, "custom_emoji_id": hot_emoji_2}
        ]
        return data
    hot_btn.to_dict = hot_to_dict
    keyboard.add(hot_btn)

    keyboard.add(styled_button(
        text=get_string('leaderboard', lang),
        callback_data="leaderboard", style="primary", emoji_id=PREMIUM_EMOJIS.get('STAR_GOLD')))

    keyboard.add(types.InlineKeyboardButton("Language", callback_data="change_lang"))

    if user_id and is_admin(user_id):
        total_users = get_total_users()
        keyboard.add(styled_button(text=f"Admin ({total_users} Members)", callback_data="none", style="primary"))

    return keyboard

@bot.callback_query_handler(func=lambda call: call.data == "back_to_start")
def handle_back_to_start(call):
    lang = get_user_language(call.from_user.id)
    welcome_text = get_string('welcome', lang)
    try:
        bot.edit_message_text(
            welcome_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=start_keyboard(call.from_user.id),
            parse_mode='HTML'
        )
    except:
        try: bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=start_keyboard(call.from_user.id))
        except: pass

@bot.callback_query_handler(func=lambda call: call.data == "change_lang")
def handle_change_lang(call):
    lang = get_user_language(call.from_user.id)
    bot.edit_message_text(
        get_string('select_language', lang),
        call.message.chat.id,
        call.message.message_id,
        reply_markup=language_keyboard()
    )

@bot.callback_query_handler(func=lambda call: call.data == "offer_menu")
def handle_offer_menu(call):
    user_id = call.from_user.id
    lang = get_user_language(user_id)

    # Get Emoji IDs
    from premium_emojis import PREMIUM_EMOJIS
    star_id = PREMIUM_EMOJIS.get('STAR_GOLD')

    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        styled_button("⭐ 100 Stars ➔ 120 Videos", callback_data="buy_120", emoji_id=star_id),
        styled_button("⭐ 250 Stars ➔ 350 Videos", callback_data="buy_350", emoji_id=star_id),
        styled_button("⭐ 500 Stars ➔ 750 Videos", callback_data="buy_750", emoji_id=star_id),
        styled_button("⭐ 1000 Stars ➔ 1600 Videos", callback_data="buy_1600", emoji_id=star_id),
        styled_button(get_string('back_to_start', lang), callback_data="back_to_start", style="primary")
    )

    bot.edit_message_text(
        PREMIUM_EMOJI_LINE + "\n✨ <b>Special Premium Offers</b> ✨\n\nChoose your pack and get instant delivery!",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=keyboard,
        parse_mode='HTML'
    )

@bot.message_handler(commands=['offer'])
def handle_offer_command(message):
    user_id = message.from_user.id
    lang = get_user_language(user_id)

    # Get Emoji IDs
    from premium_emojis import PREMIUM_EMOJIS
    star_id = PREMIUM_EMOJIS.get('STAR_GOLD')

    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        styled_button("⭐ 100 Stars ➔ 120 Videos", callback_data="buy_120", emoji_id=star_id),
        styled_button("⭐ 250 Stars ➔ 350 Videos", callback_data="buy_350", emoji_id=star_id),
        styled_button("⭐ 500 Stars ➔ 750 Videos", callback_data="buy_750", emoji_id=star_id),
        styled_button("⭐ 1000 Stars ➔ 1600 Videos", callback_data="buy_1600", emoji_id=star_id),
        styled_button(get_string('back_to_start', lang), callback_data="back_to_start", style="primary")
    )

    bot.send_message(
        message.chat.id,
        PREMIUM_EMOJI_LINE + "\n✨ <b>Special Premium Offers</b> ✨\n\nChoose your pack and get instant delivery!",
        reply_markup=keyboard,
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def handle_payment_request(call):
    user_id = call.from_user.id
    try:
        count = int(call.data.replace("buy_", ""))
    except ValueError:
        return

    # Map video counts to Star prices
    stars_map = {
        7: 7,
        65: 65,
        120: 100,
        350: 250,
        750: 500,
        1600: 1000
    }

    stars_price = stars_map.get(count, count)

    prices = [types.LabeledPrice(label=f"{count} Videos", amount=stars_price)]
    bot.send_invoice(
        call.message.chat.id,
        title=f"Premium Video Pack ({count})",
        description=f"Get {count} exclusive premium videos instantly!",
        invoice_payload=f"deliver_{user_id}_{count}",
        provider_token="", # Stars don't need provider token
        currency="XTR",
        prices=prices,
        start_parameter="premium_videos"
    )

@bot.callback_query_handler(func=lambda call: call.data == "referral_menu")
def handle_referral_menu(call):
    user_id = call.from_user.id
    lang = get_user_language(user_id)
    ref_count = get_referral_count(user_id)
    claimed_tiers = get_claimed_tiers(user_id)

    global BOT_USERNAME
    if not BOT_USERNAME: BOT_USERNAME = bot.get_me().username
    invite_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    share_text = f"🔥 Hey! I found an amazing Premium Video Bot! 🎬\n\n🎁 Get FREE videos just by joining!\n✨ Invite friends & unlock up to 750+ videos!\n⭐ Premium content delivered instantly!\n\n👇 Join now 👇\n{invite_link}"
    import urllib.parse
    share_url = f"https://t.me/share/url?url={urllib.parse.quote(invite_link)}&text={urllib.parse.quote(share_text)}"

    total_earned = sum(reward for inv, reward, _ in REFERRAL_TIERS if inv in claimed_tiers)
    progress_text = build_referral_progress(ref_count, claimed_tiers)

    text = (
        f"{PREMIUM_EMOJI_LINE}\n"
        f"{get_string('dashboard_title', lang)}\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        f"<b>{get_string('total_invites', lang)}:</b> <code>{ref_count}</code>\n"
        f"<b>{get_string('videos_earned', lang)}:</b> <code>{total_earned}</code>\n\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"{progress_text}\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        f"<b>{get_string('invite_link_label', lang)}:</b>\n<code>{invite_link}</code>\n\n"
        f"{get_string('invite_hint', lang)}"
    )

    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(styled_button(get_string('share_link', lang), url=share_url, style="success"))

    has_claimable = any(
        ref_count >= inv and inv not in claimed_tiers
        for inv, _, _ in REFERRAL_TIERS
    )
    if has_claimable:
        keyboard.add(styled_button(get_string('claim_rewards', lang), callback_data="claim_rewards", style="danger"))

    keyboard.add(styled_button(get_string('back_to_start', lang), callback_data="back_to_start", style="primary"))

    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=keyboard, parse_mode='HTML')
    except:
        try: bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=keyboard)
        except: pass

    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=keyboard, parse_mode='HTML')
    except:
        try: bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=keyboard)
        except: pass

@bot.callback_query_handler(func=lambda call: call.data == "claim_rewards")
def handle_claim_rewards(call):
    user_id = call.from_user.id
    lang = get_user_language(user_id)
    ref_count = get_referral_count(user_id)
    claimed_tiers = get_claimed_tiers(user_id)

    total_videos_to_deliver = 0
    tiers_to_claim = []

    for invites_needed, reward, name in REFERRAL_TIERS:
        if ref_count >= invites_needed and invites_needed not in claimed_tiers:
            total_videos_to_deliver += reward
            tiers_to_claim.append((invites_needed, reward, name))

    if total_videos_to_deliver == 0:
        bot.answer_callback_query(call.id, get_string('no_rewards', lang), show_alert=True)
        return

    unsent = get_unsent_videos(user_id, limit=total_videos_to_deliver)
    if not unsent:
        bot.answer_callback_query(call.id, get_string('no_videos', lang), show_alert=True)
        return

    tiers_claimed_now = []
    for invites_needed, reward, name in tiers_to_claim:
        if claim_tier(user_id, invites_needed):
            tiers_claimed_now.append((name, reward))

    if not tiers_claimed_now:
        bot.answer_callback_query(call.id, "Rewards already claimed!", show_alert=True)
        return

    tier_text = "\n".join([f"\u2705 {name}: +{reward} videos" for name, reward in tiers_claimed_now])
    bot.answer_callback_query(call.id, get_string('delivering_now', lang, count=len(unsent)))

    bot.send_message(user_id,
        f"{get_string('rewards_claimed_title', lang)}\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        f"{tier_text}\n\n"
        f"{get_string('total_incoming', lang, count=len(unsent))}",
        parse_mode='HTML')

    delivery_queue.put((user_id, unsent, notify_delivery_success, notify_delivery_failure, None))

    for admin_id in NOTIFY_IDS:
        try:
            bot.send_message(admin_id,
                f"\U0001f381 <b>Referral Reward Claimed!</b>\n\n"
                f"\U0001f464 User: <code>{user_id}</code>\n"
                f"\U0001f465 Invites: {ref_count}\n"
                f"\U0001f4e6 Videos: {len(unsent)}\n"
                f"\U0001f3c6 Tiers: {', '.join([n for n, _ in tiers_claimed_now])}",
                parse_mode='HTML')
        except: pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def handle_payment_request(call):
    user_id = call.from_user.id
    try:
        count = int(call.data.replace("buy_", ""))
    except ValueError:
        return

    # Map video counts to Star prices
    stars_map = {
        7: 7,
        65: 65,
        120: 100,
        350: 250,
        750: 500,
        1600: 1000
    }

    stars_price = stars_map.get(count, count)

    prices = [types.LabeledPrice(label=f"{count} Videos", amount=stars_price)]
    bot.send_invoice(
        call.message.chat.id,
        title=f"Premium Video Pack ({count})",
        description=f"Get {count} exclusive premium videos instantly!",
        invoice_payload=f"deliver_{user_id}_{count}",
        provider_token="", # Stars don't need provider token
        currency="XTR",
        prices=prices,
        start_parameter="premium_videos"
    )

@bot.callback_query_handler(func=lambda call: call.data == "leaderboard")
def handle_leaderboard(call):
    lang = get_user_language(call.from_user.id)
    leaders = get_referral_leaderboard(10)

    if not leaders:
        text = (
            f"{get_string('leaderboard_title', lang)}\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            f"{get_string('no_leaders', lang)}"
        )
    else:
        medals = ["\U0001f947", "\U0001f948", "\U0001f949", "4\ufe0f\u20e3", "5\ufe0f\u20e3", "6\ufe0f\u20e3", "7\ufe0f\u20e3", "8\ufe0f\u20e3", "9\ufe0f\u20e3", "\U0001f51f"]
        lines = []
        for i, (uid, uname, count) in enumerate(leaders):
            medal = medals[i] if i < len(medals) else f"#{i+1}"
            display = f"@{uname}" if uname else f"ID:{uid}"
            lines.append(f"{medal} {display} \u2014 <b>{count}</b> invites")

        text = (
            f"{get_string('leaderboard_title', lang)}\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            + "\n".join(lines) +
            f"\n\n{get_string('climb_ranks', lang)}"
        )

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(styled_button(get_string('back_to_start', lang), callback_data="back_to_start", style="primary"))

    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=keyboard, parse_mode='HTML')
    except:
        try: bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=keyboard)
        except: pass

@bot.callback_query_handler(func=lambda call: call.data == "buy_5")
def handle_purchase_5(call):
    try: bot.delete_message(call.message.chat.id, call.message.message_id)
    except: pass

    bot.send_invoice(
        call.message.chat.id,
        title="\U0001f48e Premium Package: 7 Videos",
        description="Pay 7 Stars and get 7 exclusive premium videos!",
        invoice_payload=f"deliver_{call.from_user.id}_7",
        provider_token=PROVIDER_TOKEN,
        currency="XTR",
        prices=[types.LabeledPrice(label="Stars", amount=7)]
    )

@bot.callback_query_handler(func=lambda call: call.data == "buy_50")
def handle_purchase(call):
    try: bot.delete_message(call.message.chat.id, call.message.message_id)
    except: pass

    bot.send_invoice(
        call.message.chat.id,
        title="\U0001f48e Premium Package: 65 Videos",
        description="Pay 65 Stars and get 65 exclusive premium videos!",
        invoice_payload=f"deliver_{call.from_user.id}_65",
        provider_token=PROVIDER_TOKEN,
        currency="XTR",
        prices=[types.LabeledPrice(label="Stars", amount=65)]
    )

@bot.callback_query_handler(func=lambda call: call.data == "none")
def handle_none(call):
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda message: is_banned(message.from_user.id))
def handle_banned(message):
    bot.send_message(message.chat.id, "\U0001f6ab You are banned from using this bot.")

@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    username = message.from_user.username
    is_new = False

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM users WHERE user_id = ?', (user_id,))
        if not cursor.fetchone(): 
            is_new = True
            # New user, ask for language first
            save_user(user_id, username)
            bot.send_message(message.chat.id, "Please select your language / Пожалуйста, выберите язык:", reply_markup=language_keyboard())
            # Process referral if exists
            args = message.text.split()
            if len(args) > 1 and args[1].isdigit():
                referrer_id = int(args[1])
                if referrer_id != user_id:
                    add_referral(referrer_id, user_id)
            return

    save_user(user_id, username)
    lang = get_user_language(user_id)
    welcome_text = get_string('welcome', lang)
    bot.send_message(message.chat.id, welcome_text, parse_mode='HTML', reply_markup=start_keyboard(user_id))

@bot.message_handler(commands=['check'])
def handle_check_referral(message):
    user_id = message.from_user.id
    ref_count = get_referral_count(user_id)
    claimed_tiers = get_claimed_tiers(user_id)

    global BOT_USERNAME
    if not BOT_USERNAME: BOT_USERNAME = bot.get_me().username
    invite_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"

    progress_text = build_referral_progress(ref_count, claimed_tiers)
    total_earned = sum(reward for inv, reward, _ in REFERRAL_TIERS if inv in claimed_tiers)

    text = (
        f"\U0001f3c6 <b>YOUR REFERRAL PROGRESS</b>\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        f"\U0001f465 <b>Total Invites:</b> <code>{ref_count}</code>\n"
        f"\U0001f381 <b>Videos Earned:</b> <code>{total_earned}</code>\n\n"
        f"{progress_text}\n\n"
        f"\U0001f517 <b>Invite Link:</b>\n<code>{invite_link}</code>"
    )
    bot.send_message(message.chat.id, text, parse_mode='HTML')

@bot.message_handler(commands=['logs'])
def handle_view_logs(message):
    if not is_admin(message.from_user.id): return
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT al.admin_id, u.username, al.action, al.target_id, al.timestamp 
                FROM admin_logs al
                LEFT JOIN users u ON al.admin_id = u.user_id
                ORDER BY al.timestamp DESC 
                LIMIT 20
            ''')
            logs = cursor.fetchall()

        if not logs:
            bot.reply_to(message, "No admin logs found.")
            return

        text = "\U0001f4dc <b>Recent Admin Activity</b>\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        for aid, uname, action, target, ts in logs:
            admin_display = f"@{uname}" if uname else f"ID:{aid}"
            target_display = f" (Target: {target})" if target else ""
            text += f"\U0001f464 {admin_display}\n\u2514 <b>{action}</b>{target_display}\n\U0001f552 <code>{ts}</code>\n\n"

        bot.send_message(message.chat.id, text, parse_mode='HTML')
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

@bot.message_handler(commands=['buyers'])
def handle_buyers_list(message):
    if not is_admin(message.from_user.id): return
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT u.user_id, u.username, m.total_spent 
            FROM users u
            JOIN milestones m ON u.user_id = m.user_id
            WHERE m.total_spent > 0
            ORDER BY m.total_spent DESC
            LIMIT 50
        ''')
        buyers = cursor.fetchall()

    if not buyers:
        bot.reply_to(message, "No buyers found yet.")
        return

    text = "\U0001f4b0 <b>Top Buyers</b>\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
    for uid, uname, spent in buyers:
        user_display = f"@{uname}" if uname else f"ID:{uid}"
        text += f"\U0001f464 {user_display}\n\u2514 <code>{spent}</code> Stars\n\n"

    bot.send_message(message.chat.id, text, parse_mode='HTML')

@bot.pre_checkout_query_handler(func=lambda query: True)
def checkout(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def got_payment(message):
    user_id = message.from_user.id
    lang = get_user_language(user_id)
    payload = message.successful_payment.invoice_payload
    username = message.from_user.username
    if payload.startswith("deliver_"):
        parts = payload.split('_')
        count = int(parts[2])
        unsent = get_unsent_videos(user_id, limit=count)
        if unsent:
            bot.send_message(user_id, get_string('payment_success', lang, count=len(unsent)), parse_mode='HTML')

            admin_msg_id = None
            for admin_id in NOTIFY_IDS:
                try:
                    alert = (f"{E_STAR} <b>New Purchase!</b>\n\n"
                            f"\U0001f464 User: @{username if username else 'N/A'}\n"
                            f"\U0001f194 ID: <code>{user_id}</code>\n"
                            f"\U0001f4b0 Amount: {message.successful_payment.total_amount} {message.successful_payment.currency}\n"
                            f"\U0001f4e6 Package: {len(unsent)} Videos\n"
                            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
                            f"\u23f3 Status: <b>Starting delivery...</b>")
                    sent_msg = bot.send_message(admin_id, alert, parse_mode='HTML')
                    admin_msg_id = sent_msg.message_id
                except: pass

            delivery_queue.put((user_id, unsent, notify_delivery_success, notify_delivery_failure, admin_msg_id))

            with sqlite3.connect(DATABASE) as conn:
                cursor = conn.cursor()
                cursor.execute('INSERT OR IGNORE INTO payments (user_id, payment_id, amount, currency) VALUES (?, ?, ?, ?)',
                             (user_id, message.successful_payment.telegram_payment_charge_id,
                              message.successful_payment.total_amount, message.successful_payment.currency))
                conn.commit()

            if update_user_milestone(user_id, message.successful_payment.total_amount):
                bonus_vids = get_unsent_videos(user_id, limit=100)
                if bonus_vids:
                    bot.send_message(user_id, f"\U0001f38a <b>CONGRATULATIONS!</b> \U0001f38a\n\nYou reached <b>750 Stars</b> milestone! \U0001f3c6\nHere are <b>100 BONUS Premium Videos</b> just for you! {E_HEART}", parse_mode='HTML')
                    delivery_queue.put((user_id, bonus_vids, notify_delivery_success, notify_delivery_failure, None))
                    for admin_id in NOTIFY_IDS:
                        try: bot.send_message(admin_id, f"\U0001f3c6 User {user_id} reached 750 Stars milestone and received 100 bonus videos!")
                        except: pass

@bot.message_handler(commands=['db_debug'])
def handle_db_debug(message):
    if not is_admin(message.from_user.id): return
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            total_refs = cursor.execute('SELECT COUNT(*) FROM referrals').fetchone()[0]
            top_5 = cursor.execute('''
                SELECT referrer_id, COUNT(*) as c 
                FROM referrals 
                GROUP BY referrer_id 
                ORDER BY c DESC 
                LIMIT 5
            ''').fetchall()

        text = "🔍 <b>Live DB Debug</b>\n"
        text += f"Total Referrals: {total_refs}\n\n"
        for rid, count in top_5:
            text += f"ID: <code>{rid}</code> - <b>{count}</b> invites\n"

        bot.reply_to(message, text, parse_mode='HTML')
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

@bot.message_handler(commands=['users_count'])
def handle_users_count(message):
    if not is_admin(message.from_user.id): return
    count = get_total_users()
    bot.reply_to(message, f"\U0001f4ca <b>User Count</b>\n\n\U0001f465 Total registered users: <code>{count}</code>", parse_mode='HTML')

@bot.message_handler(commands=['add'])
def handle_add_video(message):
    if not is_admin(message.from_user.id): return
    ADMIN_STATES[message.from_user.id] = 'WAITING_VIDEO'
    bot.send_message(message.chat.id, "\U0001f4e4 Send the videos you want to add. Type /done when finished.")

@bot.message_handler(content_types=['video'])
def handle_video_upload(message):
    if not is_admin(message.from_user.id) or ADMIN_STATES.get(message.from_user.id) != 'WAITING_VIDEO': return
    file_id = message.video.file_id
    file_name = message.video.file_name
    file_size = message.video.file_size
    duration = message.video.duration
    video_id = save_video(file_id, file_name, file_size, duration)

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        total_vids = cursor.execute('SELECT COUNT(*) FROM videos').fetchone()[0]

    bot.reply_to(message, f"{E_CHECK} Video added! (Number: {total_vids})")

@bot.message_handler(commands=['done'])
def handle_done(message):
    if not is_admin(message.from_user.id): return
    ADMIN_STATES[message.from_user.id] = None
    bot.send_message(message.chat.id, f"{E_CHECK} Upload session finished.")

@bot.message_handler(commands=['videos'])
def handle_videos_list(message):
    if not is_admin(message.from_user.id): return
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        total_vids = cursor.execute('SELECT COUNT(*) FROM videos').fetchone()[0]
        today_vids = cursor.execute("SELECT COUNT(*) FROM videos WHERE date(added_date) = date('now')").fetchone()[0]
        week_vids = cursor.execute("SELECT COUNT(*) FROM videos WHERE added_date >= datetime('now', '-7 days')").fetchone()[0]

    text = (
        f"\U0001f4f9 <b>Video Library Stats</b>\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        f"\U0001f4ca <b>Total Videos:</b> <code>{total_vids}</code>\n"
        f"\U0001f4c5 <b>Added Today:</b> <code>{today_vids}</code>\n"
        f"\U0001f5d3\ufe0f <b>Added This Week:</b> <code>{week_vids}</code>\n\n"
        f"\u2728 Your library is growing!"
    )
    bot.send_message(message.chat.id, text, parse_mode='HTML')

@bot.message_handler(commands=['stats'])
def handle_admin_stats(message):
    if not is_admin(message.from_user.id): return
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        total_users = cursor.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        total_vids = cursor.execute('SELECT COUNT(*) FROM videos').fetchone()[0]
        purchases = cursor.execute('SELECT COUNT(*) FROM payments').fetchone()[0]
        total_referrals = cursor.execute('SELECT COUNT(*) FROM referrals').fetchone()[0]
        total_rewards_claimed = cursor.execute('SELECT COUNT(*) FROM referral_rewards').fetchone()[0]
    bot.send_message(message.chat.id,
        f"\U0001f4ca <b>Bot Stats</b>\n\n"
        f"\U0001f465 Users: {total_users}\n"
        f"\U0001f4f9 Videos: {total_vids}\n"
        f"\U0001f6cd\ufe0f Purchases: {purchases}\n"
        f"\U0001f465 Total Referrals: {total_referrals}\n"
        f"\U0001f381 Rewards Claimed: {total_rewards_claimed}",
        parse_mode='HTML')

@bot.message_handler(commands=['ban'])
def handle_ban_command(message):
    if not is_admin(message.from_user.id): return
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "Usage: /ban <user_id>")
            return
        target_id = int(args[1])
        ban_user(target_id)
        bot.reply_to(message, f"\u2705 User {target_id} has been banned.")
        log_admin_action(message.from_user.id, "BAN", target_id=target_id)
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

@bot.message_handler(commands=['unban'])
def handle_unban_command(message):
    if not is_admin(message.from_user.id): return
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "Usage: /unban <user_id>")
            return
        target_id = int(args[1])
        unban_user(target_id)
        bot.reply_to(message, f"\u2705 User {target_id} has been unbanned.")
        log_admin_action(message.from_user.id, "UNBAN", target_id=target_id)
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

@bot.message_handler(commands=['send_v'])
def handle_send_v(message):
    if not is_admin(message.from_user.id): return
    try:
        args = message.text.split()
        if len(args) < 3:
            bot.reply_to(message, "Usage: /send_v <user_id> <count>")
            return
        target_id = int(args[1])
        video_count = int(args[2])
        unsent = get_unsent_videos(target_id, limit=video_count)
        if not unsent:
            bot.reply_to(message, "No new videos available for this user.")
            return

        status_msg = bot.send_message(message.chat.id,
            f"\U0001f680 <b>Starting Manual Delivery...</b>\n"
            f"Target: <code>{target_id}</code>\n"
            f"Count: {len(unsent)}", parse_mode='HTML')

        delivery_queue.put((target_id, unsent, notify_delivery_success, notify_delivery_failure, status_msg.message_id))
        log_admin_action(message.from_user.id, "SEND_V", target_id=target_id, details=f"Count: {video_count}")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

@bot.message_handler(commands=['top_referrers'])
def handle_top_referrers(message):
    if not is_admin(message.from_user.id): return
    leaders = get_referral_leaderboard(20)

    if not leaders:
        bot.reply_to(message, "No referrals yet.")
        return

    text = "\U0001f3c6 <b>Top Referrers (Admin View)</b>\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
    for i, (uid, uname, count) in enumerate(leaders):
        display = f"@{uname}" if uname else f"ID:{uid}"
        text += f"#{i+1} {display} \u2014 <b>{count}</b> invites (ID: <code>{uid}</code>)\n"

    bot.send_message(message.chat.id, text, parse_mode='HTML')

@bot.message_handler(commands=['broadcast_all'])
def handle_broadcast(message):
    if not is_admin(message.from_user.id): return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "Usage: /broadcast_all <message>")
        return

    broadcast_text = args[1]
    conn = sqlite3.connect(DATABASE)
    users = [r[0] for r in conn.execute('SELECT user_id FROM users').fetchall()]
    conn.close()

    success, fail = 0, 0
    for uid in users:
        try:
            bot.send_message(uid, broadcast_text, parse_mode='HTML')
            success += 1
            time.sleep(0.05)
        except:
            fail += 1

    bot.reply_to(message, f"\U0001f4e2 Broadcast Complete!\n\u2705 Success: {success}\n\u274c Failed: {fail}")
    log_admin_action(message.from_user.id, "BROADCAST_ALL", details=f"Success: {success}, Failed: {fail}")

@bot.message_handler(commands=['promo'])
def handle_promo(message):
    if not is_admin(message.from_user.id): return

    fire_line = "\U0001f525" * 10
    star_line = "\u2b50" * 10
    diamond_line = "\U0001f48e" * 10

    promo_text = (
        f"{fire_line}\n\n"
        f"\U0001f3ac <b>PREMIUM EXCLUSIVE VIDEOS</b> \U0001f3ac\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        f"\U0001f451 <b>The #1 Premium Video Bot on Telegram!</b>\n\n"
        f"\U0001f48e <b>What You Get:</b>\n"
        f"\u251c \U0001f3a5 High-quality exclusive content\n"
        f"\u251c \u26a1 Instant delivery to your chat\n"
        f"\u251c \U0001f381 FREE videos through referrals\n"
        f"\u2514 \U0001f3c6 6 reward tiers to unlock\n\n"
        f"{star_line}\n\n"
        f"\U0001f465 <b>INVITE & EARN FREE VIDEOS:</b>\n\n"
        f"\U0001f949 2 invites = 10 free videos\n"
        f"\U0001f948 5 invites = 25 free videos\n"
        f"\U0001f947 10 invites = 50 free videos\n"
        f"\U0001f48e 25 invites = 125 free videos\n"
        f"\U0001f4a0 50 invites = 250 free videos\n"
        f"\U0001f451 100 invites = 500 free videos\n"
        f"\U0001f525 200 invites = 1000 free videos\n\n"
        f"<b>Join our channel:</b> https://t.me/+Mx69KEAaOa8zOTBi\n\n"
        f"{diamond_line}\n\n"
        f"\U0001f525 <b>TOTAL: Up to 1960 FREE VIDEOS!</b> \U0001f525\n\n"
        f"\U0001f447 <b>TAP BELOW TO START NOW!</b> \U0001f447"
    )

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("\U0001f680 START THE BOT NOW \U0001f680", url="https://t.me/Llllppppooottt_bot?start=promo"))

    bot.send_message(message.chat.id, promo_text, parse_mode='HTML', reply_markup=keyboard)
    log_admin_action(message.from_user.id, "PROMO_GENERATED")

@bot.message_handler(commands=['share'])
def handle_share_broadcast(message):
    if not is_admin(message.from_user.id):
        return

    lang = 'en' # Forced English as requested
    global BOT_USERNAME
    if not BOT_USERNAME: BOT_USERNAME = bot.get_me().username
    
    invite_link = f"https://t.me/{BOT_USERNAME}?start={message.from_user.id}"
    # Motivational message with premium emojis
    share_text = f"🔥 {get_emoji_tag('FIRE', '🔥')} <b>STAY MOTIVATED!</b> {get_emoji_tag('FIRE', '🔥')}\n\n" \
                 f"✨ {get_emoji_tag('STAR_GOLD', '✨')} <b>Success is a journey, not a destination!</b>\n" \
                 f"🚀 {get_emoji_tag('PLANE', '🚀')} <b>Push yourself because no one else is going to do it for you!</b>\n\n" \
                 f"🎁 {get_emoji_tag('GIFT', '🎁')} <b>Share this bot with your friends and earn FREE premium videos!</b>\n\n" \
                 f"👇 <b>Invite & Earn Now</b> 👇"
                 
    import urllib.parse
    share_url = f"https://t.me/share/url?url={urllib.parse.quote(invite_link)}&text={urllib.parse.quote('Check out this amazing bot! 🎬')}"
    
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("📤 SHARE & EARN VIDEOS", url=share_url))
    
    # Get all users
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM users')
        users = cursor.fetchall()
        
    count = 0
    for (u_id,) in users:
        try:
            bot.send_message(u_id, share_text, parse_mode='HTML', reply_markup=keyboard)
            count += 1
            time.sleep(0.05) # Small delay to avoid flood limits
        except:
            continue
            
    bot.reply_to(message, f"✅ Broadcast sent to {count} users.")

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    save_user(message.from_user.id, message.from_user.username)

init_db()
flask_thread = Thread(target=run_flask)
flask_thread.daemon = True
flask_thread.start()

print("Bot is starting...")
while True:
    try:
        bot.remove_webhook()
        bot.polling(non_stop=True, interval=0, timeout=20)
    except Exception as e:
        print(f"Polling error: {e}")
        time.sleep(5) 
