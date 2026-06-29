import logging
import random
import sqlite3
import json
import io
from datetime import datetime as dt
from datetime import datetime
import pytz
import jdatetime
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler, ContextTypes

# ==================== تنظیمات اولیه ====================
BOT_TOKEN = "8596883196:AAH6B9H41HDCsEcq5WB9ESXkDH7qYaP93lA"
OWNER_ID = 1275490079
TEHRAN_TZ = pytz.timezone('Asia/Tehran')

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== دیتابیس ====================
def get_db_connection():
    conn = sqlite3.connect('camelot_registry.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS citizens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            telegram_username TEXT,
            telegram_first_name TEXT,
            real_name TEXT,
            gender TEXT,
            age INTEGER,
            camelot_name TEXT,
            national_id TEXT UNIQUE,
            role TEXT DEFAULT 'شهروند',
            register_date_shamsi TEXT,
            register_time TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            log_type TEXT,
            title TEXT,
            content TEXT,
            actor_id INTEGER,
            target_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT,
            message TEXT,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    defaults = [
        ('rules_text', 'قوانین سرزمین کملوت:\n1. احترام به یکدیگر\n2. همکاری با شوالیه‌ها\n3. جادو فقط در محدوده مجاز'),
        ('welcome_text', 'سلام، ای مهمان گرانقدر! 🏰✨\nبه سرزمین باشکوه و افسانه‌ای کملوت خوش آمدی... 🚪🌟'),
        ('group_link_1', 'https://t.me/YourGroup1'),
        ('group_link_2', 'https://t.me/YourGroup2'),
        ('group_link_3', 'https://t.me/YourGroup3'),
        ('group_link_4', 'https://t.me/YourGroup4'),
        ('bot_status', 'on'),
    ]
    for key, value in defaults:
        cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", (key, value))
    
    conn.commit()
    conn.close()
    print("✅ دیتابیس ثبت احوال کملوت آماده شد.")

# ==================== توابع کمکی ====================
def get_config(key):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def set_config(key, value):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def generate_unique_national_id():
    conn = get_db_connection()
    cursor = conn.cursor()
    while True:
        new_id = str(random.randint(100000, 999999))
        cursor.execute("SELECT national_id FROM citizens WHERE national_id = ?", (new_id,))
        if not cursor.fetchone():
            conn.close()
            return new_id

def get_user_by_telegram_id(tg_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM citizens WHERE telegram_id = ?", (tg_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def get_user_by_national_id(nid):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM citizens WHERE national_id = ?", (nid,))
    user = cursor.fetchone()
    conn.close()
    return user

def get_all_citizens():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM citizens ORDER BY id DESC")
    users = cursor.fetchall()
    conn.close()
    return users

def save_citizen(data):
    conn = get_db_connection()
    cursor = conn.cursor()
    national_id = generate_unique_national_id()
    now_shamsi = jdatetime.datetime.now().strftime("%Y/%m/%d")
    now_time = dt.now().strftime("%H:%M:%S")
    role = 'مالک' if data['telegram_id'] == OWNER_ID else 'شهروند'
    
    cursor.execute('''
        INSERT INTO citizens (
            telegram_id, telegram_username, telegram_first_name, real_name,
            gender, age, camelot_name, national_id, role,
            register_date_shamsi, register_time
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data['telegram_id'], data['telegram_username'], data['telegram_first_name'],
        data['real_name'], data['gender'], data['age'], data['camelot_name'],
        national_id, role, now_shamsi, now_time
    ))
    conn.commit()
    conn.close()
    return national_id

def update_user_field(telegram_id, field, value):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"UPDATE citizens SET {field} = ? WHERE telegram_id = ?", (value, telegram_id))
    conn.commit()
    conn.close()

def exile_citizen(telegram_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE citizens SET national_id = NULL, role = 'شهروند' WHERE telegram_id = ?", (telegram_id,))
    conn.commit()
    conn.close()

def add_system_log(log_type, title, content, actor_id=None, target_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO system_logs (log_type, title, content, actor_id, target_id)
        VALUES (?, ?, ?, ?, ?)
    ''', (log_type, title, content, actor_id, target_id))
    conn.commit()
    conn.close()

def get_system_logs(limit=50, offset=0):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM system_logs 
        ORDER BY created_at DESC 
        LIMIT ? OFFSET ?
    ''', (limit, offset))
    logs = cursor.fetchall()
    cursor.execute("SELECT COUNT(*) FROM system_logs")
    total = cursor.fetchone()[0]
    conn.close()
    return logs, total

def add_notification(telegram_id, title, message):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM citizens WHERE telegram_id = ?", (telegram_id,))
    user = cursor.fetchone()
    if user:
        cursor.execute('''
            INSERT INTO notifications (user_id, title, message)
            VALUES (?, ?, ?)
        ''', (user['id'], title, message))
        conn.commit()
    conn.close()

def get_notifications(user_id, limit=20):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM notifications 
        WHERE user_id = ? 
        ORDER BY created_at DESC 
        LIMIT ?
    ''', (user_id, limit))
    notifs = cursor.fetchall()
    conn.close()
    return notifs

def mark_notification_read(notif_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notif_id,))
    conn.commit()
    conn.close()

def export_full_backup():
    conn = get_db_connection()
    cursor = conn.cursor()
    backup_data = {
        'version': '1.0',
        'created_at': dt.now(TEHRAN_TZ).isoformat(),
        'tables': {}
    }
    for table in ['citizens', 'system_logs', 'config', 'notifications']:
        cursor.execute(f"SELECT * FROM {table}")
        rows = cursor.fetchall()
        table_data = []
        for row in rows:
            row_dict = dict(row)
            for key, value in row_dict.items():
                if isinstance(value, datetime):
                    row_dict[key] = value.isoformat()
            table_data.append(row_dict)
        backup_data['tables'][table] = table_data
    conn.close()
    return json.dumps(backup_data, ensure_ascii=False, indent=2)

def import_full_backup(json_data):
    try:
        backup_data = json.loads(json_data)
    except:
        return False, "فرمت JSON نامعتبر است"
    if 'tables' not in backup_data:
        return False, "ساختار پشتیبان نامعتبر است"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    for table in ['citizens', 'system_logs', 'config', 'notifications']:
        cursor.execute(f"DELETE FROM {table}")
    for table, rows in backup_data['tables'].items():
        if rows:
            columns = list(rows[0].keys())
            placeholders = ','.join(['?'] * len(columns))
            columns_str = ','.join([f'"{col}"' for col in columns])
            for row in rows:
                values = [row.get(col) for col in columns]
                try:
                    cursor.execute(f"INSERT OR REPLACE INTO {table} ({columns_str}) VALUES ({placeholders})", values)
                except Exception as e:
                    pass
    conn.commit()
    conn.close()
    return True, "بازیابی با موفقیت انجام شد"

# ==================== توابع کمکی نمایش ====================
def get_jalali_date():
    now = datetime.now(TEHRAN_TZ)
    jnow = jdatetime.datetime.fromgregorian(datetime=now)
    return jnow.strftime("%Y/%m/%d - %H:%M")

def get_role_display(role):
    roles = {'شهروند':'شهروند', 'کارمند':'کارمند', 'شاه':'شاه', 'مالک':'مالک'}
    return roles.get(role, 'شهروند')

def is_bot_online(user_id=None):
    status = get_config('bot_status')
    if user_id == OWNER_ID:
        return True
    return status != 'off'

# ==================== منوی اصلی ====================
def main_menu_keyboard(user_id):
    if not is_bot_online(user_id):
        return None
    keyboard = [
        [InlineKeyboardButton("👤 اطلاعات من", callback_data="my_info")],
        [InlineKeyboardButton("📬 صندوق پیام", callback_data="notifications")],
    ]
    if user_id == OWNER_ID:
        keyboard.append([InlineKeyboardButton("👑 پنل مدیریت", callback_data="panel")])
    else:
        user = get_user_by_telegram_id(user_id)
        if user and user['role'] == 'کارمند':
            keyboard.append([InlineKeyboardButton("👑 پنل مدیریت", callback_data="panel")])
    return InlineKeyboardMarkup(keyboard)

# ==================== شروع و ثبت‌نام ====================
(WELCOME, WAITING_REAL_NAME, WAITING_GENDER, WAITING_CAMELOT_NAME,
 WAITING_AGE, CONFIRM_INFO, WAITING_RULES_ACCEPT) = range(7)

RESTORE_BACKUP_STATE = 800
REPORT_REASON = 700
EDIT_RULES_STATE = 900
EDIT_WELCOME_STATE = 950

async def start(update: Update, context):
    user_id = update.effective_user.id
    existing_user = get_user_by_telegram_id(user_id)
    
    if existing_user:
        await update.message.reply_text(
            f"🏰 شما از قبل به سرزمین کملوت پیوسته‌اید.\n"
            f"🪪 کد ملی شما: `{existing_user['national_id']}` می‌باشد.",
            parse_mode='Markdown',
            reply_markup=main_menu_keyboard(user_id)
        )
        return ConversationHandler.END
    
    if user_id == OWNER_ID:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 بازگردانی پشتیبان", callback_data="restore_backup")],
            [InlineKeyboardButton("📝 ثبت‌نام جدید", callback_data="start_registration")]
        ])
        await update.message.reply_text(
            "🏰 **به سرزمین کملوت خوش آمدید، مالک گرامی!**\n\n"
            "• اگر قبلاً پشتیبان دارید، روی «بازگردانی پشتیبان» کلیک کنید.\n"
            "• اگر می‌خواهید ثبت‌نام کنید، روی «ثبت‌نام جدید» کلیک کنید.",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        return WELCOME
    
    if not is_bot_online(user_id):
        await update.message.reply_text("⛔ ربات در حال حاضر خاموش است. لطفاً بعداً تلاش کنید.")
        return
    
    welcome_text = get_config('welcome_text') or "سلام، ای مهمان گرانقدر! 🏰✨\nبه سرزمین باشکوه و افسانه‌ای کملوت خوش آمدی... 🚪🌟"
    keyboard = [[InlineKeyboardButton("بزن بریم 🚀", callback_data="start_registration")]]
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard))
    return WELCOME

async def start_registration_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("✍️ لطفاً **اسم واقعی** خود را وارد کن:")
    return WAITING_REAL_NAME

async def receive_real_name(update: Update, context):
    context.user_data['real_name'] = update.message.text.strip()
    keyboard = [
        [InlineKeyboardButton("👧 دختر", callback_data="gender_girl")],
        [InlineKeyboardButton("👦 پسر", callback_data="gender_boy")]
    ]
    await update.message.reply_text("⚧️ جنسیت خود را انتخاب کن:", reply_markup=InlineKeyboardMarkup(keyboard))
    return WAITING_GENDER

async def receive_gender_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    gender = "دختر" if query.data == "gender_girl" else "پسر"
    context.user_data['gender'] = gender
    await query.message.reply_text(f"✅ جنسیت شما: {gender}\n🗡️ حالا **نام کملوتی** خود را انتخاب کن:")
    return WAITING_CAMELOT_NAME

async def receive_camelot_name(update: Update, context):
    context.user_data['camelot_name'] = update.message.text.strip()
    await update.message.reply_text("🎂 **سن واقعی** خود را به عدد وارد کن:")
    return WAITING_AGE

async def receive_age(update: Update, context):
    try:
        age = int(update.message.text.strip())
        if age < 0 or age > 150:
            raise ValueError
        context.user_data['age'] = age
    except:
        await update.message.reply_text("❌ لطفاً یک عدد معتبر (بین ۰ تا ۱۵۰) وارد کن.")
        return WAITING_AGE
    
    data = context.user_data
    summary = (
        f"📋 **فرم ثبت‌نام شما**\n─────────────────\n"
        f"👤 اسم واقعی: {data['real_name']}\n"
        f"⚧️ جنسیت: {data['gender']}\n"
        f"🗡️ نام کملوتی: {data['camelot_name']}\n"
        f"🎂 سن: {data['age']}\n─────────────────\n"
        f"⚠️ **توجه**: این اطلاعات قابل تغییر نیست.\n"
        f"آیا تایید می‌کنی؟"
    )
    keyboard = [
        [InlineKeyboardButton("✅ تایید و ادامه", callback_data="confirm_yes")],
        [InlineKeyboardButton("❌ لغو (بازگشت به اول)", callback_data="confirm_no")]
    ]
    await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return CONFIRM_INFO

async def confirm_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "confirm_no":
        welcome_text = get_config('welcome_text') or "سلام، ای مهمان گرانقدر! 🏰✨ ..."
        keyboard = [[InlineKeyboardButton("بزن بریم 🚀", callback_data="start_registration")]]
        await query.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard))
        return WELCOME
    
    rules_text = get_config('rules_text') or "قوانین کملوت"
    keyboard = [
        [InlineKeyboardButton("✅ تایید میکنم", callback_data="rules_accept")],
        [InlineKeyboardButton("❌ لغو", callback_data="rules_cancel")]
    ]
    await query.message.reply_text(
        f"📜 **قوانین سرزمین کملوت**\n\n{rules_text}\n\nبا ادامه دادن، تمامی قوانین را می‌پذیرید.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return WAITING_RULES_ACCEPT

async def rules_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "rules_cancel":
        welcome_text = get_config('welcome_text') or "سلام، ای مهمان گرانقدر! ..."
        keyboard = [[InlineKeyboardButton("بزن بریم 🚀", callback_data="start_registration")]]
        await query.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard))
        return WELCOME
    
    user = update.effective_user
    data = {
        'telegram_id': user.id,
        'telegram_username': user.username or "ندارد",
        'telegram_first_name': user.first_name or "ندارد",
        'real_name': context.user_data['real_name'],
        'gender': context.user_data['gender'],
        'age': context.user_data['age'],
        'camelot_name': context.user_data['camelot_name']
    }
    national_id = save_citizen(data)
    add_system_log('registration', 'ثبت‌نام جدید', f'کاربر: {data["camelot_name"]} - کد ملی: {national_id}', actor_id=user.id)
    
    await query.message.reply_text(
        f"📝 درخواست شهروندی شما با موفقیت ثبت و تایید شد.\n\n🪪 کد ملی شما: `{national_id}`",
        parse_mode='Markdown'
    )
    
    links = [get_config(f'group_link_{i}') or f'https://t.me/Group{i}' for i in range(1,5)]
    keyboard = [[InlineKeyboardButton(f"🏰 گروه {i+1}", url=link)] for i, link in enumerate(links)]
    await query.message.reply_text(
        "خوش آمدید! با استفاده از دکمه‌های زیر، وارد سرزمین شوید.\n\nبه امید موفقیت شما ✨🏰",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data.clear()
    return ConversationHandler.END

# ==================== بازگردانی پشتیبان برای مالک ====================
async def restore_backup_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await query.edit_message_text("⛔ دسترسی ندارید.")
        return
    await query.edit_message_text(
        "📤 **بازگردانی پشتیبان**\n\n"
        "لطفاً فایل JSON پشتیبان را ارسال کنید.\n"
        "(برای لغو /cancel بزنید)",
        parse_mode='Markdown'
    )
    return RESTORE_BACKUP_STATE

async def restore_backup_file(update: Update, context):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("⛔ دسترسی ندارید.")
        return ConversationHandler.END
    doc = update.message.document
    if not doc or not doc.file_name.endswith('.json'):
        await update.message.reply_text("❌ لطفاً یک فایل JSON معتبر ارسال کنید.")
        return RESTORE_BACKUP_STATE
    await update.message.reply_text("📥 در حال بازیابی...", parse_mode='Markdown')
    try:
        file = await context.bot.get_file(doc.file_id)
        content = (await file.download_as_bytearray()).decode('utf-8')
        success, msg = import_full_backup(content)
        if success:
            add_system_log('admin_action', 'بازگردانی پشتیبان', 'توسط: مالک', actor_id=user_id)
            await update.message.reply_text(f"✅ {msg}", reply_markup=main_menu_keyboard(user_id))
        else:
            await update.message.reply_text(f"❌ {msg}", reply_markup=main_menu_keyboard(user_id))
    except Exception as e:
        await update.message.reply_text(f"❌ خطا: {str(e)}", reply_markup=main_menu_keyboard(user_id))
    return ConversationHandler.END

# ==================== توابع اصلی کاربر ====================
async def my_info_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    user = get_user_by_telegram_id(user_id)
    if not user:
        await query.edit_message_text("❌ شما ثبت‌نام نکرده‌اید.")
        return
    if not is_bot_online(user_id):
        await query.edit_message_text("⛔ ربات در حال حاضر خاموش است.")
        return
    info_text = f"""👤 **اطلاعات شما**
━━━━━━━━━━━━━━━━━━━
📛 نام واقعی: {user['real_name']}
⚧️ جنسیت: {user['gender']}
🎂 سن: {user['age']}
🗡️ نام کملوتی: {user['camelot_name']}
🆔 کد ملی: {user['national_id']}
👑 نقش: {get_role_display(user['role'])}
📅 تاریخ ثبت: {user['register_date_shamsi']} - {user['register_time']}
━━━━━━━━━━━━━━━━━━━
"""
    await query.edit_message_text(info_text, reply_markup=main_menu_keyboard(user_id), parse_mode='Markdown')

async def notifications_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_bot_online(user_id):
        await query.edit_message_text("⛔ ربات در حال حاضر خاموش است.")
        return
    user = get_user_by_telegram_id(user_id)
    if not user:
        await query.edit_message_text("❌ شما ثبت‌نام نکرده‌اید.")
        return
    notifs = get_notifications(user['id'])
    if not notifs:
        await query.edit_message_text("📬 **صندوق پیام شما خالی است.**", reply_markup=main_menu_keyboard(user_id))
        return
    text = "📬 **صندوق پیام شما**\n━━━━━━━━━━━━━━━━━━━\n\n"
    for n in notifs:
        created = datetime.strptime(n['created_at'], '%Y-%m-%d %H:%M:%S')
        jcreated = jdatetime.datetime.fromgregorian(datetime=created)
        date_str = jcreated.strftime('%Y/%m/%d - %H:%M')
        status_icon = "✅" if n['is_read'] else "🔵"
        text += f"{status_icon} **{n['title']}**\n"
        text += f"📝 {n['message']}\n"
        text += f"🕐 {date_str}\n━━━━━━━━━━━━━━━━━━━\n"
        if not n['is_read']:
            mark_notification_read(n['id'])
    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def back_to_menu(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    await query.edit_message_text("🏰 منوی اصلی کملوت", reply_markup=main_menu_keyboard(user_id))

# ==================== پنل مدیریت ====================
async def panel_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    user = get_user_by_telegram_id(user_id)
    if not user:
        await query.edit_message_text("❌ شما ثبت‌نام نکرده‌اید.")
        return
    
    role = user['role']
    
    if role == 'مالک':
        keyboard = [
            [InlineKeyboardButton("👥 مدیریت کاربران", callback_data="admin_users")],
            [InlineKeyboardButton("📜 تغییر قوانین", callback_data="admin_edit_rules")],
            [InlineKeyboardButton("💬 تغییر پیام خوش‌آمد", callback_data="admin_edit_welcome")],
            [InlineKeyboardButton("📣 ارسال پیام همگانی", callback_data="admin_broadcast")],
            [InlineKeyboardButton("📋 لاگ‌های سیستم", callback_data="admin_logs")],
            [InlineKeyboardButton("💾 پشتیبان‌گیری و بازیابی", callback_data="admin_backup")],
            [InlineKeyboardButton("🔴 خاموش/روشن کردن ربات", callback_data="admin_toggle_bot")],
            [InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_menu")],
        ]
    elif role == 'کارمند':
        keyboard = [
            [InlineKeyboardButton("👥 مدیریت کاربران", callback_data="admin_users")],
            [InlineKeyboardButton("📣 ارسال پیام همگانی", callback_data="admin_broadcast")],
            [InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_menu")],
        ]
    else:
        await query.edit_message_text("⛔ شما دسترسی به پنل مدیریت ندارید.", reply_markup=main_menu_keyboard(user_id))
        return
    
    await query.edit_message_text(
        f"👑 **پنل مدیریت ({get_role_display(role)})**\n🕐 {get_jalali_date()}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ==================== تغییر قوانین ====================
async def admin_edit_rules_start(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await query.edit_message_text("⛔ دسترسی ندارید.")
        return
    current = get_config('rules_text') or "قوانین کملوت"
    await query.edit_message_text(
        f"📜 **قوانین فعلی:**\n{current}\n\n"
        "لطفاً متن جدید قوانین را وارد کنید:\n"
        "(برای لغو /cancel بزنید)",
        parse_mode='Markdown'
    )
    return EDIT_RULES_STATE

async def admin_edit_rules_receive(update: Update, context):
    text = update.message.text
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("⛔ دسترسی ندارید.")
        return ConversationHandler.END
    if text.lower() == '/cancel':
        await update.message.reply_text("❌ تغییر قوانین لغو شد.", reply_markup=main_menu_keyboard(user_id))
        return ConversationHandler.END
    
    set_config('rules_text', text)
    add_system_log('admin_action', 'تغییر قوانین', f'متن جدید: {text[:100]}...', actor_id=user_id)
    await update.message.reply_text(
        "✅ **قوانین با موفقیت به‌روز شد.**",
        reply_markup=main_menu_keyboard(user_id)
    )
    return ConversationHandler.END

# ==================== تغییر پیام خوش‌آمد ====================
async def admin_edit_welcome_start(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await query.edit_message_text("⛔ دسترسی ندارید.")
        return
    current = get_config('welcome_text') or "پیام خوش‌آمد پیش‌فرض"
    await query.edit_message_text(
        f"💬 **پیام خوش‌آمد فعلی:**\n{current}\n\n"
        "لطفاً متن جدید پیام خوش‌آمد را وارد کنید:\n"
        "(برای لغو /cancel بزنید)",
        parse_mode='Markdown'
    )
    return EDIT_WELCOME_STATE

async def admin_edit_welcome_receive(update: Update, context):
    text = update.message.text
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("⛔ دسترسی ندارید.")
        return ConversationHandler.END
    if text.lower() == '/cancel':
        await update.message.reply_text("❌ تغییر پیام خوش‌آمد لغو شد.", reply_markup=main_menu_keyboard(user_id))
        return ConversationHandler.END
    
    set_config('welcome_text', text)
    add_system_log('admin_action', 'تغییر پیام خوش‌آمد', f'متن جدید: {text[:100]}...', actor_id=user_id)
    await update.message.reply_text(
        "✅ **پیام خوش‌آمد با موفقیت به‌روز شد.**",
        reply_markup=main_menu_keyboard(user_id)
    )
    return ConversationHandler.END

# ==================== خاموش/روشن کردن ربات ====================
async def admin_toggle_bot(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await query.edit_message_text("⛔ دسترسی ندارید.")
        return
    current = get_config('bot_status')
    new_status = 'off' if current != 'off' else 'on'
    set_config('bot_status', new_status)
    status_text = "خاموش" if new_status == 'off' else "روشن"
    add_system_log('admin_action', f'ربات {status_text} شد', f'توسط: مالک', actor_id=user_id)
    await query.edit_message_text(
        f"✅ ربات با موفقیت {status_text} شد.\nوضعیت فعلی: {'🔴 خاموش' if new_status == 'off' else '🟢 روشن'}",
        reply_markup=main_menu_keyboard(user_id),
        parse_mode='Markdown'
    )

# ==================== مدیریت کاربران ====================
USERS_PER_PAGE = 10
LOGS_PER_PAGE = 10
ADMIN_EDIT_STATE = 200
ADMIN_BROADCAST_STATE = 300
ADMIN_BACKUP_STATE = 500
ADMIN_USER_MANAGE_STATE = 600

async def admin_users_list(update: Update, context):
    """لیست کاربران با دسترسی‌های متفاوت برای مالک و کارمند"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user = get_user_by_telegram_id(user_id)
    if not user or user['role'] not in ['مالک', 'کارمند']:
        await query.edit_message_text("⛔ دسترسی ندارید.")
        return
    
    all_users = get_all_citizens()
    total = len(all_users)
    
    if total == 0:
        await query.edit_message_text(
            "📭 **هیچ شهروندی ثبت‌نام نکرده است.**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_panel")]
            ]),
            parse_mode='Markdown'
        )
        return
    
    is_owner = (user['role'] == 'مالک')
    text = "👥 **لیست کاربران کملوت**\n━━━━━━━━━━━━━━━━━━━\n"
    
    for idx, u in enumerate(all_users[:20], 1):
        text += f"**{idx}. {u['real_name']}** ({u['camelot_name']})\n"
        text += f"🆔 کدملی: {u['national_id'] or '—'}\n"
        text += f"🎂 سن: {u['age'] if u['age'] else 'ثبت نشده'}\n"
        text += f"⚧️ جنسیت: {u['gender']}\n"
        text += f"👑 نقش: {get_role_display(u['role'])}\n"
        if is_owner:
            text += f"📱 آیدی: {u['telegram_id']}\n"
            text += f"📱 یوزرنیم: @{u['telegram_username'] or 'ندارد'}\n"
            text += f"📅 ثبت: {u['register_date_shamsi']} - {u['register_time']}\n"
        text += f"━━━━━━━━━━━━━━━━━━━\n"
    
    if len(all_users) > 20:
        text += f"\n... و {len(all_users) - 20} کاربر دیگر"
    
    keyboard = [
        [InlineKeyboardButton("🔍 مدیریت کاربر با آیدی", callback_data="admin_manage_user")],
        [InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="back_to_panel")],
    ]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ==================== مدیریت کاربر با آیدی ====================
async def admin_manage_user_start(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    user = get_user_by_telegram_id(user_id)
    if not user or user['role'] not in ['مالک', 'کارمند']:
        await query.edit_message_text("⛔ دسترسی ندارید.")
        return
    await query.edit_message_text(
        "🔍 **مدیریت کاربر با آیدی تلگرام**\n\n"
        "لطفاً آیدی عددی تلگرام کاربر را وارد کنید:\n"
        "(برای لغو /cancel بزنید)",
        parse_mode='Markdown'
    )
    return ADMIN_USER_MANAGE_STATE

async def admin_manage_user_receive(update: Update, context):
    text = update.message.text.strip()
    user_id = update.effective_user.id
    user = get_user_by_telegram_id(user_id)
    if not user or user['role'] not in ['مالک', 'کارمند']:
        await update.message.reply_text("⛔ دسترسی ندارید.")
        return ConversationHandler.END
    if text.lower() == '/cancel':
        await update.message.reply_text("❌ لغو شد.", reply_markup=main_menu_keyboard(user_id))
        return ConversationHandler.END
    if not text.isdigit():
        await update.message.reply_text("❌ آیدی باید عدد باشد. دوباره وارد کنید:")
        return ADMIN_USER_MANAGE_STATE
    
    target_telegram_id = int(text)
    target_user = get_user_by_telegram_id(target_telegram_id)
    if not target_user:
        await update.message.reply_text("❌ کاربری با این آیدی یافت نشد. دوباره وارد کنید:")
        return ADMIN_USER_MANAGE_STATE
    
    context.user_data['manage_target'] = target_telegram_id
    is_owner = (user['role'] == 'مالک')
    
    # اطلاعات پایه (مشترک برای مالک و کارمند)
    info_text = f"""👤 **اطلاعات کاربر**
━━━━━━━━━━━━━━━━━━━
📛 **نام واقعی:** {target_user['real_name']}
⚧️ **جنسیت:** {target_user['gender']}
🎂 **سن:** {target_user['age'] if target_user['age'] else 'ثبت نشده'}
🗡️ **نام کملوتی:** {target_user['camelot_name']}
🆔 **کد ملی:** {target_user['national_id']}
👑 **نقش:** {get_role_display(target_user['role'])}
"""
    if is_owner:
        info_text += f"""📱 **آیدی تلگرام:** {target_user['telegram_id']}
📱 **یوزرنیم:** @{target_user['telegram_username'] or 'ندارد'}
📅 **تاریخ ثبت:** {target_user['register_date_shamsi']} - {target_user['register_time']}
"""
    info_text += "━━━━━━━━━━━━━━━━━━━"
    
    # دکمه‌ها بر اساس نقش
    if is_owner:
        keyboard = [
            [InlineKeyboardButton("✏️ تغییر نام واقعی", callback_data=f"admin_edit_realname_{target_telegram_id}")],
            [InlineKeyboardButton("✏️ تغییر نام کملوتی", callback_data=f"admin_edit_camelot_{target_telegram_id}")],
            [InlineKeyboardButton("✏️ تغییر سن", callback_data=f"admin_edit_age_{target_telegram_id}")],
            [InlineKeyboardButton("✏️ تغییر یوزرنیم", callback_data=f"admin_edit_username_{target_telegram_id}")],
            [InlineKeyboardButton("✏️ تغییر کد ملی", callback_data=f"admin_edit_national_{target_telegram_id}")],
            [InlineKeyboardButton("👑 تغییر نقش", callback_data=f"admin_change_role_{target_telegram_id}")],
            [InlineKeyboardButton("🚫 اخراج شهروند", callback_data=f"admin_exile_{target_telegram_id}")],
            [InlineKeyboardButton("📨 گزارش به مدیریت", callback_data=f"admin_report_{target_telegram_id}")],
            [InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="admin_users")],
        ]
    else:  # کارمند
        keyboard = [
            [InlineKeyboardButton("✏️ تغییر نام واقعی", callback_data=f"admin_edit_realname_{target_telegram_id}")],
            [InlineKeyboardButton("✏️ تغییر نام کملوتی", callback_data=f"admin_edit_camelot_{target_telegram_id}")],
            [InlineKeyboardButton("✏️ تغییر سن", callback_data=f"admin_edit_age_{target_telegram_id}")],
            [InlineKeyboardButton("📨 گزارش به مدیریت", callback_data=f"admin_report_{target_telegram_id}")],
            [InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="admin_users")],
        ]
    
    await update.message.reply_text(info_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return ConversationHandler.END

# ==================== توابع ویرایش فیلدها ====================
async def admin_edit_field_start(update: Update, context, field_name, target_telegram_id):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    user = get_user_by_telegram_id(user_id)
    if not user or user['role'] not in ['مالک', 'کارمند']:
        await query.edit_message_text("⛔ دسترسی ندارید.")
        return
    
    # کارمند فقط می‌تونه نام واقعی، نام کملوتی و سن رو تغییر بده
    if user['role'] == 'کارمند' and field_name not in ['real_name', 'camelot', 'age']:
        await query.edit_message_text("⛔ شما اجازه تغییر این فیلد را ندارید.")
        return
    
    context.user_data['edit_field'] = field_name
    context.user_data['edit_target'] = target_telegram_id
    field_names = {
        'real_name': 'نام واقعی',
        'camelot': 'نام کملوتی',
        'age': 'سن',
        'username': 'یوزرنیم',
        'national': 'کد ملی'
    }
    await query.edit_message_text(
        f"✏️ **تغییر {field_names.get(field_name, field_name)}**\n\n"
        f"لطفاً مقدار جدید را وارد کنید:\n"
        f"(برای لغو /cancel بزنید)",
        parse_mode='Markdown'
    )
    return ADMIN_EDIT_STATE

async def admin_edit_value(update: Update, context):
    text = update.message.text.strip()
    user_id = update.effective_user.id
    user = get_user_by_telegram_id(user_id)
    if not user or user['role'] not in ['مالک', 'کارمند']:
        await update.message.reply_text("⛔ دسترسی ندارید.")
        return ConversationHandler.END
    if text.lower() == '/cancel':
        await update.message.reply_text("❌ تغییر لغو شد.", reply_markup=main_menu_keyboard(user_id))
        context.user_data.pop('edit_field', None)
        context.user_data.pop('edit_target', None)
        return ConversationHandler.END
    
    field = context.user_data.get('edit_field')
    target = context.user_data.get('edit_target')
    if not field or not target:
        await update.message.reply_text("❌ خطا: اطلاعات ناقص.")
        return ConversationHandler.END
    
    old_user = get_user_by_telegram_id(target)
    if not old_user:
        await update.message.reply_text("❌ کاربر یافت نشد.")
        return ConversationHandler.END
    
    if field == 'real_name':
        update_user_field(target, 'real_name', text)
        add_system_log('admin_action', f'تغییر نام واقعی {old_user["camelot_name"]}', f'نام جدید: {text}', actor_id=user_id, target_id=target)
        add_notification(target, 'تغییر اطلاعات', f'نام واقعی شما توسط مدیریت به `{text}` تغییر یافت.')
        try:
            await context.bot.send_message(target, f"📝 **اطلاعات شما توسط مدیریت تغییر کرد.**\nنام واقعی جدید: `{text}`", parse_mode='Markdown')
        except: pass
        await update.message.reply_text(f"✅ نام واقعی به `{text}` تغییر یافت.", parse_mode='Markdown')
    
    elif field == 'camelot':
        update_user_field(target, 'camelot_name', text)
        add_system_log('admin_action', f'تغییر نام کملوتی {old_user["camelot_name"]}', f'نام جدید: {text}', actor_id=user_id, target_id=target)
        add_notification(target, 'تغییر اطلاعات', f'نام کملوتی شما توسط مدیریت به `{text}` تغییر یافت.')
        try:
            await context.bot.send_message(target, f"📝 **اطلاعات شما توسط مدیریت تغییر کرد.**\nنام کملوتی جدید: `{text}`", parse_mode='Markdown')
        except: pass
        await update.message.reply_text(f"✅ نام کملوتی به `{text}` تغییر یافت.", parse_mode='Markdown')
    
    elif field == 'age':
        try:
            age = int(text)
            if age < 0 or age > 150: raise ValueError
            update_user_field(target, 'age', age)
            add_system_log('admin_action', f'تغییر سن {old_user["camelot_name"]}', f'سن جدید: {age}', actor_id=user_id, target_id=target)
            add_notification(target, 'تغییر اطلاعات', f'سن شما توسط مدیریت به `{age}` تغییر یافت.')
            try:
                await context.bot.send_message(target, f"📝 **اطلاعات شما توسط مدیریت تغییر کرد.**\nسن جدید: `{age}`", parse_mode='Markdown')
            except: pass
            await update.message.reply_text(f"✅ سن به `{age}` تغییر یافت.", parse_mode='Markdown')
        except:
            await update.message.reply_text("❌ عدد بین ۰ تا ۱۵۰ وارد کن.")
            return ADMIN_EDIT_STATE
    
    elif field == 'username':
        # فقط مالک
        if user['role'] != 'مالک':
            await update.message.reply_text("⛔ دسترسی ندارید.")
            return ConversationHandler.END
        new_un = text.lstrip('@')
        update_user_field(target, 'telegram_username', new_un)
        add_system_log('admin_action', f'تغییر یوزرنیم {old_user["camelot_name"]}', f'یوزرنیم جدید: @{new_un}', actor_id=user_id, target_id=target)
        add_notification(target, 'تغییر اطلاعات', f'یوزرنیم شما توسط مدیریت به @{new_un} تغییر یافت.')
        try:
            await context.bot.send_message(target, f"📝 **اطلاعات شما توسط مدیریت تغییر کرد.**\nیوزرنیم جدید: @{new_un}", parse_mode='Markdown')
        except: pass
        await update.message.reply_text(f"✅ یوزرنیم به `@{new_un}` تغییر یافت.", parse_mode='Markdown')
    
    elif field == 'national':
        # فقط مالک
        if user['role'] != 'مالک':
            await update.message.reply_text("⛔ دسترسی ندارید.")
            return ConversationHandler.END
        if len(text) != 6 or not text.isdigit():
            await update.message.reply_text("❌ کد ملی ۶ رقم است.")
            return ADMIN_EDIT_STATE
        existing = get_user_by_national_id(text)
        if existing and existing['telegram_id'] != target:
            await update.message.reply_text("❌ این کد ملی قبلاً ثبت شده.")
            return ADMIN_EDIT_STATE
        update_user_field(target, 'national_id', text)
        add_system_log('admin_action', f'تغییر کد ملی {old_user["camelot_name"]}', f'کد جدید: {text}', actor_id=user_id, target_id=target)
        add_notification(target, 'تغییر اطلاعات', f'کد ملی شما توسط مدیریت به `{text}` تغییر یافت.')
        try:
            await context.bot.send_message(target, f"📝 **اطلاعات شما توسط مدیریت تغییر کرد.**\nکد ملی جدید: `{text}`", parse_mode='Markdown')
        except: pass
        await update.message.reply_text(f"✅ کد ملی به `{text}` تغییر یافت.", parse_mode='Markdown')
    
    context.user_data.pop('edit_field', None)
    context.user_data.pop('edit_target', None)
    return ConversationHandler.END

# ==================== تغییر نقش (فقط مالک) ====================
async def admin_change_role(update: Update, context, target_telegram_id):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await query.edit_message_text("⛔ دسترسی ندارید.")
        return
    
    target_user = get_user_by_telegram_id(target_telegram_id)
    if not target_user:
        await query.edit_message_text("❌ کاربر یافت نشد.")
        return
    
    roles = ['شهروند', 'کارمند', 'شاه']
    keyboard = []
    for role in roles:
        if role != target_user['role']:
            keyboard.append([InlineKeyboardButton(f"👑 {role}", callback_data=f"admin_set_role_{target_telegram_id}_{role}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_users")])
    
    await query.edit_message_text(
        f"👤 **کاربر:** {target_user['real_name']} ({target_user['camelot_name']})\n"
        f"نقش فعلی: {get_role_display(target_user['role'])}\n\n"
        f"نقش جدید را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def admin_set_role(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await query.edit_message_text("⛔ دسترسی ندارید.")
        return
    
    parts = query.data.split('_')
    target = int(parts[3])
    new_role = parts[4]
    
    target_user = get_user_by_telegram_id(target)
    if not target_user:
        await query.edit_message_text("❌ کاربر یافت نشد.")
        return
    
    update_user_field(target, 'role', new_role)
    add_system_log('admin_action', f'تغییر نقش {target_user["camelot_name"]}', f'نقش جدید: {new_role}', actor_id=user_id, target_id=target)
    add_notification(target, 'تغییر نقش', f'نقش شما توسط مدیریت به {get_role_display(new_role)} تغییر یافت.')
    try:
        await context.bot.send_message(target, f"📝 **نقش شما توسط مدیریت تغییر کرد.**\nنقش جدید: {get_role_display(new_role)}", parse_mode='Markdown')
    except: pass
    await query.edit_message_text(
        f"✅ نقش {target_user['camelot_name']} به **{get_role_display(new_role)}** تغییر یافت.",
        reply_markup=main_menu_keyboard(user_id),
        parse_mode='Markdown'
    )

# ==================== اخراج شهروند (فقط مالک) ====================
async def admin_exile_user(update: Update, context, target_telegram_id):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await query.edit_message_text("⛔ دسترسی ندارید.")
        return
    
    user = get_user_by_telegram_id(target_telegram_id)
    if not user:
        await query.edit_message_text("❌ کاربر یافت نشد.")
        return
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ بله، اخراج کن", callback_data=f"admin_exile_confirm_{target_telegram_id}")],
        [InlineKeyboardButton("❌ لغو", callback_data="admin_cancel_exile")]
    ])
    await query.edit_message_text(
        f"⚠️ **تأیید اخراج شهروند**\n\n"
        f"کاربر: {user['camelot_name']} (نام واقعی: {user['real_name']})\n"
        f"کد ملی فعلی: {user['national_id']}\n\n"
        f"آیا از اخراج این شهروند مطمئن هستید؟",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

async def admin_exile_confirm(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await query.edit_message_text("⛔ دسترسی ندارید.")
        return
    target = int(query.data.split('_')[3])
    user = get_user_by_telegram_id(target)
    if not user:
        await query.edit_message_text("❌ کاربر یافت نشد.")
        return
    exile_citizen(target)
    add_system_log('admin_action', f'اخراج {user["camelot_name"]}', f'کد ملی قبلی: {user["national_id"]}', actor_id=user_id, target_id=target)
    add_notification(target, 'اخراج از کملوت', f'شما از سرزمین کملوت اخراج شدید. کد ملی شما آزاد شد.')
    try:
        await context.bot.send_message(target, f"🚫 **شما از سرزمین کملوت اخراج شدید.**\nکد ملی شما آزاد شد.", parse_mode='Markdown')
    except: pass
    await query.edit_message_text(
        f"✅ {user['camelot_name']} اخراج شد. کد ملی آزاد شد.",
        reply_markup=main_menu_keyboard(user_id),
        parse_mode='Markdown'
    )

async def admin_cancel_exile(update: Update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ لغو شد.", reply_markup=main_menu_keyboard(update.effective_user.id))

# ==================== گزارش کارمند به مالک ====================
async def admin_report_start(update: Update, context, target_telegram_id):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    user = get_user_by_telegram_id(user_id)
    if not user or user['role'] not in ['کارمند', 'مالک']:
        await query.edit_message_text("⛔ فقط کارمندان و مالک می‌توانند گزارش دهند.")
        return
    context.user_data['report_target'] = target_telegram_id
    await query.edit_message_text(
        "📨 **ارسال گزارش به مدیریت**\n\n"
        "لطفاً دلیل گزارش خود را بنویسید:\n"
        "(برای لغو /cancel بزنید)",
        parse_mode='Markdown'
    )
    return REPORT_REASON

async def admin_report_reason(update: Update, context):
    text = update.message.text.strip()
    user_id = update.effective_user.id
    if text.lower() == '/cancel':
        await update.message.reply_text("❌ گزارش لغو شد.", reply_markup=main_menu_keyboard(user_id))
        return ConversationHandler.END
    
    target = context.user_data.get('report_target')
    if not target:
        await update.message.reply_text("❌ خطا: هدف گزارش یافت نشد.")
        return ConversationHandler.END
    
    target_user = get_user_by_telegram_id(target)
    actor = get_user_by_telegram_id(user_id)
    if not target_user or not actor:
        await update.message.reply_text("❌ کاربر یافت نشد.")
        return ConversationHandler.END
    
    report_text = f"""📨 **گزارش جدید از سوی {get_role_display(actor['role'])}**

👤 **گزارش‌دهنده:** {actor['real_name']} ({actor['camelot_name']})
🆔 آیدی: {actor['telegram_id']}
👑 نقش: {get_role_display(actor['role'])}

━━━━━━━━━━━━━━━━━━━
**اطلاعات کاربر مورد گزارش:**

👤 **نام واقعی:** {target_user['real_name']}
🗡️ **نام کملوتی:** {target_user['camelot_name']}
🆔 **کد ملی:** {target_user['national_id']}
👑 **نقش:** {get_role_display(target_user['role'])}
📱 **آیدی تلگرام:** {target_user['telegram_id']}
━━━━━━━━━━━━━━━━━━━

📝 **دلیل گزارش:**
{text}

🕐 **زمان:** {get_jalali_date()}
"""
    try:
        await context.bot.send_message(OWNER_ID, report_text, parse_mode='Markdown')
        await update.message.reply_text(
            f"✅ گزارش شما با موفقیت به مدیریت ارسال شد.\nکاربر: {target_user['camelot_name']}",
            reply_markup=main_menu_keyboard(user_id)
        )
        add_system_log('report', f'گزارش درباره {target_user["camelot_name"]}', f'دلیل: {text}', actor_id=user_id, target_id=target)
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در ارسال گزارش: {str(e)}", reply_markup=main_menu_keyboard(user_id))
    context.user_data.pop('report_target', None)
    return ConversationHandler.END

# ==================== ارسال پیام همگانی ====================
async def admin_broadcast_start(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    user = get_user_by_telegram_id(user_id)
    if not user or user['role'] not in ['مالک', 'کارمند']:
        await query.edit_message_text("⛔ دسترسی ندارید.")
        return
    await query.edit_message_text(
        "📣 **ارسال پیام همگانی**\n\n"
        "لطفاً متن پیام را وارد کنید:\n"
        "(برای لغو /cancel بزنید)",
        parse_mode='Markdown'
    )
    return ADMIN_BROADCAST_STATE

async def admin_broadcast_receive(update: Update, context):
    text = update.message.text
    user_id = update.effective_user.id
    user = get_user_by_telegram_id(user_id)
    if not user or user['role'] not in ['مالک', 'کارمند']:
        await update.message.reply_text("⛔ دسترسی ندارید.")
        return ConversationHandler.END
    if text.lower() == '/cancel':
        await update.message.reply_text("❌ ارسال پیام لغو شد.", reply_markup=main_menu_keyboard(user_id))
        return ConversationHandler.END
    
    all_users = get_all_citizens()
    if not all_users:
        await update.message.reply_text("❌ هیچ کاربری برای ارسال پیام وجود ندارد.")
        return ConversationHandler.END
    
    await update.message.reply_text(f"📣 در حال ارسال به {len(all_users)} کاربر... لطفاً صبر کنید.", parse_mode='Markdown')
    success = 0
    fail = 0
    for u in all_users:
        try:
            await context.bot.send_message(
                u['telegram_id'],
                f"📣 **پیام همگانی کملوت**\n\n{text}",
                parse_mode='Markdown'
            )
            add_notification(u['telegram_id'], 'پیام همگانی', text)
            success += 1
        except:
            fail += 1
        await asyncio.sleep(0.05)
    
    add_system_log('admin_action', 'ارسال پیام همگانی', f'موفق: {success} - ناموفق: {fail}', actor_id=user_id)
    await update.message.reply_text(
        f"✅ **پیام همگانی ارسال شد.**\nموفق: {success}\nناموفق: {fail}",
        reply_markup=main_menu_keyboard(user_id)
    )
    return ConversationHandler.END

# ==================== لاگ‌های سیستم (فقط مالک) ====================
async def admin_logs_list(update: Update, context, page=0):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await query.edit_message_text("⛔ دسترسی ندارید.")
        return
    
    offset = page * LOGS_PER_PAGE
    logs, total = get_system_logs(LOGS_PER_PAGE, offset)
    if not logs:
        await query.edit_message_text(
            "📭 **هیچ لاگی ثبت نشده است.**",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_panel")]])
        )
        return
    
    text = f"📋 **لاگ‌های سیستم**\n━━━━━━━━━━━━━━━━━━━\nتعداد کل: {total} | صفحه {page+1}\n━━━━━━━━━━━━━━━━━━━\n\n"
    for log in logs:
        created = datetime.strptime(log['created_at'], '%Y-%m-%d %H:%M:%S')
        jcreated = jdatetime.datetime.fromgregorian(datetime=created)
        date_str = jcreated.strftime('%Y/%m/%d - %H:%M')
        text += f"📌 **{log['title']}**\n"
        text += f"📝 {log['content'][:100]}{'...' if len(log['content']) > 100 else ''}\n"
        text += f"🕐 {date_str}\n━━━━━━━━━━━━━━━━━━━\n"
    
    keyboard = []
    nav_buttons = []
    total_pages = (total + LOGS_PER_PAGE - 1) // LOGS_PER_PAGE
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ قبلی", callback_data=f"admin_logs_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("➡️ بعدی", callback_data=f"admin_logs_page_{page+1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="back_to_panel")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def admin_logs_page_handler(update: Update, context):
    query = update.callback_query
    page = int(query.data.split('_')[3])
    await admin_logs_list(update, context, page)

# ==================== پشتیبان‌گیری و بازیابی (فقط مالک) ====================
async def admin_backup_menu(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await query.edit_message_text("⛔ دسترسی ندارید.")
        return
    keyboard = [
        [InlineKeyboardButton("📥 گرفتن پشتیبان", callback_data="admin_backup_export")],
        [InlineKeyboardButton("📤 بازیابی از پشتیبان", callback_data="admin_backup_import")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_panel")],
    ]
    await query.edit_message_text(
        "💾 **پشتیبان‌گیری و بازیابی**\n\n"
        "• گرفتن پشتیبان: خروجی JSON کامل از دیتابیس\n"
        "• بازیابی: ارسال فایل JSON برای بازگردانی اطلاعات\n\n"
        "⚠️ بازیابی تمام اطلاعات فعلی را بازنویسی می‌کند!",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def admin_backup_export(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await query.edit_message_text("⛔ دسترسی ندارید.")
        return
    await query.edit_message_text("📥 در حال تهیه پشتیبان...", parse_mode='Markdown')
    try:
        json_data = export_full_backup()
        file_obj = io.BytesIO(json_data.encode('utf-8'))
        file_obj.name = f"camelot_registry_backup_{dt.now(TEHRAN_TZ).strftime('%Y%m%d_%H%M%S')}.json"
        await context.bot.send_document(
            chat_id=user_id,
            document=file_obj,
            caption=f"💾 پشتیبان ثبت احوال کملوت\n🕐 {get_jalali_date()}"
        )
        add_system_log('admin_action', 'گرفتن پشتیبان', f'توسط: مالک', actor_id=user_id)
        await query.edit_message_text(
            "✅ پشتیبان با موفقیت تهیه و ارسال شد.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_backup")]])
        )
    except Exception as e:
        await query.edit_message_text(f"❌ خطا: {str(e)}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_backup")]]))

async def admin_backup_import_start(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await query.edit_message_text("⛔ دسترسی ندارید.")
        return
    await query.edit_message_text(
        "📤 **بازیابی از پشتیبان**\n\n"
        "لطفاً فایل JSON را ارسال کنید:\n"
        "(برای لغو /cancel بزنید)",
        parse_mode='Markdown'
    )
    return ADMIN_BACKUP_STATE

async def admin_backup_import_file(update: Update, context):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("⛔ دسترسی ندارید.")
        return ConversationHandler.END
    document = update.message.document
    if not document or not document.file_name.endswith('.json'):
        await update.message.reply_text("❌ لطفاً یک فایل JSON معتبر ارسال کنید.")
        return ADMIN_BACKUP_STATE
    await update.message.reply_text("📥 در حال دریافت فایل...", parse_mode='Markdown')
    try:
        file = await context.bot.get_file(document.file_id)
        content = await file.download_as_bytearray()
        json_data = content.decode('utf-8')
        success, msg = import_full_backup(json_data)
        if success:
            add_system_log('admin_action', 'بازیابی از پشتیبان', f'توسط: مالک', actor_id=user_id)
            await update.message.reply_text(
                f"✅ {msg}",
                reply_markup=main_menu_keyboard(user_id)
            )
        else:
            await update.message.reply_text(f"❌ {msg}", reply_markup=main_menu_keyboard(user_id))
    except Exception as e:
        await update.message.reply_text(f"❌ خطا: {str(e)}", reply_markup=main_menu_keyboard(user_id))
    return ConversationHandler.END

# ==================== main ====================
def main():
    init_db()
    if get_config('bot_status') is None:
        set_config('bot_status', 'on')
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # ---------- ثبت‌نام ----------
    reg_conv = ConversationHandler(
        entry_points=[CommandHandler('start', start), CallbackQueryHandler(start_registration_callback, pattern='^start_registration$')],
        states={
            WELCOME: [CallbackQueryHandler(start_registration_callback, pattern='^start_registration$')],
            WAITING_REAL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_real_name)],
            WAITING_GENDER: [CallbackQueryHandler(receive_gender_callback, pattern='^gender_')],
            WAITING_CAMELOT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_camelot_name)],
            WAITING_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_age)],
            CONFIRM_INFO: [CallbackQueryHandler(confirm_callback, pattern='^confirm_')],
            WAITING_RULES_ACCEPT: [CallbackQueryHandler(rules_callback, pattern='^(rules_accept|rules_cancel)$')],
        },
        fallbacks=[CommandHandler('start', start), CommandHandler('cancel', start)],
    )
    app.add_handler(reg_conv)
    
    # ---------- بازگردانی پشتیبان ----------
    restore_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(restore_backup_callback, pattern='^restore_backup$')],
        states={RESTORE_BACKUP_STATE: [MessageHandler(filters.Document.ALL, restore_backup_file)]},
        fallbacks=[CommandHandler('start', start), CommandHandler('cancel', start)],
    )
    app.add_handler(restore_conv)
    
    # ---------- تغییر قوانین ----------
    edit_rules_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_edit_rules_start, pattern='^admin_edit_rules$')],
        states={EDIT_RULES_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit_rules_receive)]},
        fallbacks=[CommandHandler('start', start), CommandHandler('cancel', start)],
    )
    app.add_handler(edit_rules_conv)
    
    # ---------- تغییر پیام خوش‌آمد ----------
    edit_welcome_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_edit_welcome_start, pattern='^admin_edit_welcome$')],
        states={EDIT_WELCOME_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit_welcome_receive)]},
        fallbacks=[CommandHandler('start', start), CommandHandler('cancel', start)],
    )
    app.add_handler(edit_welcome_conv)
    
    # ---------- مدیریت کاربر با آیدی ----------
    manage_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_manage_user_start, pattern='^admin_manage_user$')],
        states={ADMIN_USER_MANAGE_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_manage_user_receive)]},
        fallbacks=[CommandHandler('start', start), CommandHandler('cancel', start)],
    )
    app.add_handler(manage_conv)
    
    # ---------- ویرایش فیلدها ----------
    edit_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(lambda u,c: admin_edit_field_start(u,c, 'real_name', int(u.callback_query.data.split('_')[3])), pattern='^admin_edit_realname_'),
            CallbackQueryHandler(lambda u,c: admin_edit_field_start(u,c, 'camelot', int(u.callback_query.data.split('_')[3])), pattern='^admin_edit_camelot_'),
            CallbackQueryHandler(lambda u,c: admin_edit_field_start(u,c, 'age', int(u.callback_query.data.split('_')[3])), pattern='^admin_edit_age_'),
            CallbackQueryHandler(lambda u,c: admin_edit_field_start(u,c, 'username', int(u.callback_query.data.split('_')[3])), pattern='^admin_edit_username_'),
            CallbackQueryHandler(lambda u,c: admin_edit_field_start(u,c, 'national', int(u.callback_query.data.split('_')[3])), pattern='^admin_edit_national_'),
        ],
        states={ADMIN_EDIT_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit_value)]},
        fallbacks=[CommandHandler('start', start), CommandHandler('cancel', start)],
    )
    app.add_handler(edit_conv)
    
    # ---------- گزارش ----------
    report_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(lambda u,c: admin_report_start(u,c, int(u.callback_query.data.split('_')[3])), pattern='^admin_report_')],
        states={REPORT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_report_reason)]},
        fallbacks=[CommandHandler('start', start), CommandHandler('cancel', start)],
    )
    app.add_handler(report_conv)
    
    # ---------- ارسال پیام همگانی ----------
    broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_broadcast_start, pattern='^admin_broadcast$')],
        states={ADMIN_BROADCAST_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_receive)]},
        fallbacks=[CommandHandler('start', start), CommandHandler('cancel', start)],
    )
    app.add_handler(broadcast_conv)
    
    # ---------- پشتیبان‌گیری ----------
    backup_import_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_backup_import_start, pattern='^admin_backup_import$')],
        states={ADMIN_BACKUP_STATE: [MessageHandler(filters.Document.ALL, admin_backup_import_file)]},
        fallbacks=[CommandHandler('start', start), CommandHandler('cancel', start)],
    )
    app.add_handler(backup_import_conv)
    
    # ---------- کالبک‌های اصلی ----------
    app.add_handler(CallbackQueryHandler(panel_callback, pattern='^panel$'))
    app.add_handler(CallbackQueryHandler(admin_users_list, pattern='^admin_users$'))
    app.add_handler(CallbackQueryHandler(my_info_callback, pattern='^my_info$'))
    app.add_handler(CallbackQueryHandler(notifications_callback, pattern='^notifications$'))
    app.add_handler(CallbackQueryHandler(back_to_menu, pattern='^back_to_menu$'))
    app.add_handler(CallbackQueryHandler(back_to_menu, pattern='^back_to_panel$'))
    
    app.add_handler(CallbackQueryHandler(admin_logs_list, pattern='^admin_logs$'))
    app.add_handler(CallbackQueryHandler(admin_logs_page_handler, pattern='^admin_logs_page_'))
    app.add_handler(CallbackQueryHandler(admin_backup_menu, pattern='^admin_backup$'))
    app.add_handler(CallbackQueryHandler(admin_backup_export, pattern='^admin_backup_export$'))
    app.add_handler(CallbackQueryHandler(admin_toggle_bot, pattern='^admin_toggle_bot$'))
    
    # تغییر نقش
    app.add_handler(CallbackQueryHandler(lambda u,c: admin_change_role(u,c, int(u.callback_query.data.split('_')[3])), pattern='^admin_change_role_'))
    app.add_handler(CallbackQueryHandler(admin_set_role, pattern='^admin_set_role_'))
    
    # اخراج
    app.add_handler(CallbackQueryHandler(lambda u,c: admin_exile_user(u,c, int(u.callback_query.data.split('_')[3])), pattern='^admin_exile_'))
    app.add_handler(CallbackQueryHandler(admin_exile_confirm, pattern='^admin_exile_confirm_'))
    app.add_handler(CallbackQueryHandler(admin_cancel_exile, pattern='^admin_cancel_exile$'))
    
    print("✅ ربات ثبت احوال کملوت با تمام تغییرات راه‌اندازی شد!")
    app.run_polling()

if __name__ == '__main__':
    main()