import logging
import random
import sqlite3
import json
import io
from datetime import datetime as dt
from datetime import datetime
import pytz
import jdatetime
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
    
    # جدول شهروندان
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
    
    # جدول لاگ‌های سیستم
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
    
    # جدول تنظیمات
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # مقداردهی اولیه تنظیمات
    cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", ('rules_text', 'قوانین سرزمین کملوت:\n1. احترام به یکدیگر\n2. همکاری با شوالیه‌ها\n3. جادو فقط در محدوده مجاز'))
    cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", ('group_link_1', 'https://t.me/YourGroup1'))
    cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", ('group_link_2', 'https://t.me/YourGroup2'))
    cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", ('group_link_3', 'https://t.me/YourGroup3'))
    cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", ('group_link_4', 'https://t.me/YourGroup4'))
    
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
    # کد ملی را NULL می‌کنیم و نقش را به شهروند تغییر می‌دهیم
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

def export_full_backup():
    conn = get_db_connection()
    cursor = conn.cursor()
    backup_data = {
        'version': '1.0',
        'created_at': dt.now(TEHRAN_TZ).isoformat(),
        'tables': {}
    }
    for table in ['citizens', 'system_logs', 'config']:
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
    # پاک کردن جداول
    for table in ['citizens', 'system_logs', 'config']:
        cursor.execute(f"DELETE FROM {table}")
    # درج داده‌ها
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
                    logger.warning(f"خطا در درج {table}: {e}")
    conn.commit()
    conn.close()
    return True, "بازیابی با موفقیت انجام شد"

# ==================== وضعیت ربات ====================
def is_bot_online():
    status = get_config('bot_status')
    return status != 'off'

def set_bot_status(status):
    set_config('bot_status', status)

# ==================== توابع کمکی نمایش ====================
def get_jalali_date():
    now = datetime.now(TEHRAN_TZ)
    jnow = jdatetime.datetime.fromgregorian(datetime=now)
    return jnow.strftime("%Y/%m/%d - %H:%M")

def get_role_display(role):
    roles = {'شهروند':'شهروند', 'کارمند':'کارمند', 'شاه':'شاه', 'مالک':'مالک'}
    return roles.get(role, 'شهروند')

# ==================== منوی اصلی ====================
def main_menu_keyboard(user_id):
    if not is_bot_online() and user_id != OWNER_ID:
        return None
    keyboard = [
        [InlineKeyboardButton("💰 موجودی", callback_data="balance")],
        [InlineKeyboardButton("👤 اطلاعات من", callback_data="my_info")],
        [InlineKeyboardButton("📬 صندوق پیام", callback_data="notifications")],
        [InlineKeyboardButton("🆘 پشتیبانی", callback_data="support")],
    ]
    if user_id == OWNER_ID:
        keyboard.append([InlineKeyboardButton("👑 پنل مدیریت", callback_data="panel")])
    return InlineKeyboardMarkup(keyboard)

# ==================== شروع و ثبت‌نام ====================
(WELCOME, WAITING_REAL_NAME, WAITING_GENDER, WAITING_CAMELOT_NAME,
 WAITING_AGE, CONFIRM_INFO, WAITING_RULES_ACCEPT) = range(7)

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
    
    if not is_bot_online() and user_id != OWNER_ID:
        await update.message.reply_text("⛔ ربات در حال حاضر خاموش است. لطفاً بعداً تلاش کنید.")
        return
    
    welcome_text = (
        "سلام، ای مهمان گرانقدر! 🏰✨\n"
        "به سرزمین باشکوه و افسانه‌ای کملوت خوش آمدی، جایی که شاه آرتور بزرگ بر تخت طلایی می‌نشیند "
        "و مرلین جادوگر از اعماق غار خرد خود بر ما نگهبانی می‌کند! 🧙‍♂️👑\n"
        "برای آنکه نامت در سپرهای درخشان این سرزمین ثبت شود و شهروندی شرافتمند باشی، "
        "نخست باید شناسنامه‌ای از جنس نور دریافت کنی و کد ملی‌ات را از سنگ‌های جادویی بگیری "
        "تا دروازه‌های کملوت به روت گشوده شود و از نعمت‌های پادشاهی بهره‌مند گردی! ⚔️🛡️\n"
        "آیا دلت می‌خواهد نامت را در تاریخ کملوت بنویسی؟ آنگاه بر دکمه‌ای که در پیش روی توست بزن "
        "و به درون این سرزمین افسانه‌ای گام نه! 🚪🌟"
    )
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
    await update.message.reply_text(
        "⚧️ جنسیت خود را انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_GENDER

async def receive_gender_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    gender = "دختر" if query.data == "gender_girl" else "پسر"
    context.user_data['gender'] = gender
    await query.message.reply_text(
        f"✅ جنسیت شما: {gender}\n"
        "🗡️ حالا **نام کملوتی** خود را (نام مستعار در سرزمین) انتخاب کن:"
    )
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
        f"📋 **فرم ثبت‌نام شما**\n"
        f"─────────────────\n"
        f"👤 اسم واقعی: {data['real_name']}\n"
        f"⚧️ جنسیت: {data['gender']}\n"
        f"🗡️ نام کملوتی: {data['camelot_name']}\n"
        f"🎂 سن: {data['age']}\n"
        f"─────────────────\n"
        f"⚠️ **توجه**: این اطلاعات قابل تغییر نیست.\n"
        f"اگر اشتباه وارد کرده باشی، طبق قانون کملوت، مجازیم به جرم ارائه اطلاعات غلط و مخفی‌کاری، "
        f"شناسنامه‌ات را باطل و حق شهروندی‌ات را ازت بگیریم.\n"
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
        welcome_text = (
            "سلام، ای مهمان گرانقدر! 🏰✨\n"
            "به سرزمین باشکوه و افسانه‌ای کملوت خوش آمدی... (همان متن قبلی)"
        )
        keyboard = [[InlineKeyboardButton("بزن بریم 🚀", callback_data="start_registration")]]
        await query.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard))
        return WELCOME
    
    rules_text = get_config('rules_text') or "قوانین کملوت (مقدار پیش‌فرض)"
    keyboard = [
        [InlineKeyboardButton("✅ تایید میکنم", callback_data="rules_accept")],
        [InlineKeyboardButton("❌ لغو", callback_data="rules_cancel")]
    ]
    await query.message.reply_text(
        f"📜 **قوانین سرزمین کملوت**\n\n{rules_text}\n\n"
        "با ادامه دادن و ثبت نهایی اطلاعات و دریافت کد ملی، شما تمامی قوانین ما را می‌پذیرید و ملزم به رعایت آنها هستید و قبول میکنید در صورت تخلف و دادگاهی شدن در این سرزمین، حکم دادگاه را می‌پذیرید.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return WAITING_RULES_ACCEPT

async def rules_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    if query.data == "rules_cancel":
        welcome_text = "سلام، ای مهمان گرانقدر! ... (متن خوش‌آمد)"
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
        f"📝 درخواست شهروندی شما با موفقیت ثبت و تایید شد.\n\n"
        f"🪪 کد ملی شما: `{national_id}`",
        parse_mode='Markdown'
    )
    
    links = [
        get_config('group_link_1') or 'https://t.me/YourGroup1',
        get_config('group_link_2') or 'https://t.me/YourGroup2',
        get_config('group_link_3') or 'https://t.me/YourGroup3',
        get_config('group_link_4') or 'https://t.me/YourGroup4'
    ]
    keyboard = [
        [InlineKeyboardButton(f"🏰 گروه {i+1}", url=link)] for i, link in enumerate(links)
    ]
    await query.message.reply_text(
        "خوش آمدید! با استفاده از دکمه‌های زیر، وارد سرزمین شوید.\n\n"
        "به امید موفقیت شما ✨🏰",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data.clear()
    return ConversationHandler.END

# ==================== توابع اصلی کاربر ====================
async def balance_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    user = get_user_by_telegram_id(user_id)
    if not user:
        await query.edit_message_text("❌ شما ثبت‌نام نکرده‌اید. لطفاً /start کنید.")
        return
    if not is_bot_online() and user_id != OWNER_ID:
        await query.edit_message_text("⛔ ربات در حال حاضر خاموش است.")
        return
    # در این ربات موجودی معنی ندارد، ولی برای نمایش پیام دوستانه:
    await query.edit_message_text(
        f"💰 **موجودی شما در بانک کملوت**\n\n"
        f"شما به عنوان شهروند کملوت، هیچ موجودی بانکی ندارید، اما اعتبار شما نزد پادشاهی محفوظ است! ⚔️\n"
        f"برای اطلاعات بیشتر به پنل اصلی بروید.",
        reply_markup=main_menu_keyboard(user_id),
        parse_mode='Markdown'
    )

async def my_info_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    user = get_user_by_telegram_id(user_id)
    if not user:
        await query.edit_message_text("❌ شما ثبت‌نام نکرده‌اید. لطفاً /start کنید.")
        return
    if not is_bot_online() and user_id != OWNER_ID:
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
📅 تاریخ ثبت‌نام: {user['register_date_shamsi']} - {user['register_time']}
━━━━━━━━━━━━━━━━━━━
"""
    await query.edit_message_text(info_text, reply_markup=main_menu_keyboard(user_id), parse_mode='Markdown')

async def notifications_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📬 **صندوق پیام شما خالی است.**\n\n"
        "هیچ اعلانی برای شما وجود ندارد.",
        reply_markup=main_menu_keyboard(update.effective_user.id),
        parse_mode='Markdown'
    )

async def support_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    user = get_user_by_telegram_id(user_id)
    if not user:
        await query.edit_message_text("❌ شما ثبت‌نام نکرده‌اید. لطفاً /start کنید.")
        return
    await query.edit_message_text(
        "🆘 **پشتیبانی کملوت**\n\n"
        "لطفاً پیام خود را به صورت یک پیام متنی ارسال کنید.\n"
        "مدیریت در اسرع وقت پاسخ خواهد داد.",
        reply_markup=main_menu_keyboard(user_id),
        parse_mode='Markdown'
    )

# ==================== پنل مدیریت (فقط مالک) ====================
async def panel_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await query.edit_message_text("⛔ دسترسی ندارید.")
        return
    if not is_bot_online():
        await query.edit_message_text("⛔ ربات در حال حاضر خاموش است.")
        return
    
    keyboard = [
        [InlineKeyboardButton("👥 مدیریت کاربران", callback_data="admin_users")],
        [InlineKeyboardButton("📣 ارسال پیام همگانی", callback_data="admin_broadcast")],
        [InlineKeyboardButton("📋 لیست همه اعضا", callback_data="admin_users")],  # همان مدیریت کاربران
        [InlineKeyboardButton("📋 لاگ‌های سیستم", callback_data="admin_logs")],
        [InlineKeyboardButton("💾 پشتیبان‌گیری و بازیابی", callback_data="admin_backup")],
        [InlineKeyboardButton("🔴 خاموش/روشن کردن ربات", callback_data="admin_toggle_bot")],
        [InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_menu")],
    ]
    await query.edit_message_text(
        f"👑 **پنل مدیریت**\n🕐 {get_jalali_date()}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def admin_toggle_bot(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await query.edit_message_text("⛔ دسترسی ندارید.")
        return
    current = get_config('bot_status')
    new_status = 'off' if current != 'off' else 'on'
    set_bot_status(new_status)
    status_text = "خاموش" if new_status == 'off' else "روشن"
    add_system_log('admin_action', f'ربات {status_text} شد', f'توسط: مالک', actor_id=user_id)
    await query.edit_message_text(
        f"✅ ربات با موفقیت {status_text} شد.\nوضعیت فعلی: {'🔴 خاموش' if new_status == 'off' else '🟢 روشن'}",
        reply_markup=main_menu_keyboard(user_id),
        parse_mode='Markdown'
    )

async def back_to_menu(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    await query.edit_message_text(
        "🏰 منوی اصلی کملوت",
        reply_markup=main_menu_keyboard(user_id),
        parse_mode='Markdown'
    )

# ==================== مدیریت کاربران (لیست و ویرایش) ====================
USERS_PER_PAGE = 10
ADMIN_EDIT_STATE = 200
ADMIN_BROADCAST_STATE = 300
ADMIN_LOGS_PAGE = 400
ADMIN_BACKUP_STATE = 500
ADMIN_USER_MANAGE_STATE = 600

async def admin_users_list(update: Update, context, page=0):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await query.edit_message_text("⛔ دسترسی ندارید.")
        return
    
    all_users = get_all_citizens()
    total = len(all_users)
    if total == 0:
        await query.edit_message_text(
            "📭 **هیچ شهروندی ثبت‌نام نکرده است.**",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_panel")]]),
            parse_mode='Markdown'
        )
        return
    
    offset = page * USERS_PER_PAGE
    users_page = all_users[offset:offset+USERS_PER_PAGE]
    
    text = f"👥 **لیست شهروندان کملوت**\n━━━━━━━━━━━━━━━━━━━\n"
    text += f"تعداد کل: {total} | صفحه {page+1}\n━━━━━━━━━━━━━━━━━━━\n\n"
    
    for idx, u in enumerate(users_page, start=offset+1):
        text += f"**{idx}. {u['real_name']}** ({u['camelot_name']})\n"
        text += f"🆔 کدملی: {u['national_id']}\n"
        text += f"🎂 سن: {u['age'] if u['age'] else 'ثبت نشده'}\n"
        text += f"👑 نقش: {get_role_display(u['role'])}\n"
        text += f"📱 آیدی: {u['telegram_id']}\n"
        text += f"📅 ثبت: {u['register_date_shamsi']}\n"
        text += f"━━━━━━━━━━━━━━━━━━━\n"
    
    keyboard = []
    nav_buttons = []
    total_pages = (total + USERS_PER_PAGE - 1) // USERS_PER_PAGE
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ قبلی", callback_data=f"admin_users_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("➡️ بعدی", callback_data=f"admin_users_page_{page+1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append([InlineKeyboardButton("🔍 مدیریت کاربر با آیدی", callback_data="admin_manage_user")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="back_to_panel")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def admin_users_page_handler(update: Update, context):
    query = update.callback_query
    page = int(query.data.split('_')[3])
    await admin_users_list(update, context, page)

async def admin_manage_user_start(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
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
    if user_id != OWNER_ID:
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
    
    info_text = f"""👤 **اطلاعات کاربر**
━━━━━━━━━━━━━━━━━━━
📛 **نام واقعی:** {target_user['real_name']}
⚧️ **جنسیت:** {target_user['gender']}
🎂 **سن:** {target_user['age'] if target_user['age'] else 'ثبت نشده'}
🗡️ **نام کملوتی:** {target_user['camelot_name']}
🆔 **کد ملی:** {target_user['national_id']}
👑 **نقش:** {get_role_display(target_user['role'])}
📱 **آیدی تلگرام:** {target_user['telegram_id']}
📱 **یوزرنیم:** @{target_user['telegram_username'] or 'ندارد'}
📅 **تاریخ ثبت:** {target_user['register_date_shamsi']} - {target_user['register_time']}
━━━━━━━━━━━━━━━━━━━
"""
    keyboard = [
        [InlineKeyboardButton("✏️ تغییر نام واقعی", callback_data=f"admin_edit_realname_{target_telegram_id}")],
        [InlineKeyboardButton("✏️ تغییر نام کملوتی", callback_data=f"admin_edit_camelot_{target_telegram_id}")],
        [InlineKeyboardButton("✏️ تغییر سن", callback_data=f"admin_edit_age_{target_telegram_id}")],
        [InlineKeyboardButton("✏️ تغییر یوزرنیم", callback_data=f"admin_edit_username_{target_telegram_id}")],
        [InlineKeyboardButton("✏️ تغییر کد ملی", callback_data=f"admin_edit_national_{target_telegram_id}")],
        [InlineKeyboardButton("👑 تغییر نقش", callback_data=f"admin_change_role_{target_telegram_id}")],
        [InlineKeyboardButton("🚫 اخراج شهروند", callback_data=f"admin_exile_{target_telegram_id}")],
        [InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="admin_users")],
    ]
    await update.message.reply_text(info_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return ConversationHandler.END

# ==================== توابع ویرایش فیلدها ====================
async def admin_edit_field_start(update: Update, context, field_name, target_telegram_id):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await query.edit_message_text("⛔ دسترسی ندارید.")
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
    if user_id != OWNER_ID:
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
        add_system_log('admin_action', f'تغییر نام واقعی کاربر {old_user["camelot_name"]}', f'نام جدید: {text}', actor_id=user_id, target_id=target)
        await update.message.reply_text(f"✅ نام واقعی با موفقیت به `{text}` تغییر یافت.", parse_mode='Markdown')
    
    elif field == 'camelot':
        update_user_field(target, 'camelot_name', text)
        add_system_log('admin_action', f'تغییر نام کملوتی کاربر {old_user["camelot_name"]}', f'نام جدید: {text}', actor_id=user_id, target_id=target)
        await update.message.reply_text(f"✅ نام کملوتی با موفقیت به `{text}` تغییر یافت.", parse_mode='Markdown')
    
    elif field == 'age':
        try:
            new_age = int(text)
            if new_age < 0 or new_age > 150:
                raise ValueError
            update_user_field(target, 'age', new_age)
            add_system_log('admin_action', f'تغییر سن کاربر {old_user["camelot_name"]}', f'سن جدید: {new_age}', actor_id=user_id, target_id=target)
            await update.message.reply_text(f"✅ سن با موفقیت به `{new_age}` تغییر یافت.", parse_mode='Markdown')
        except:
            await update.message.reply_text("❌ سن باید عددی بین ۰ تا ۱۵۰ باشد. دوباره وارد کنید:")
            return ADMIN_EDIT_STATE
    
    elif field == 'username':
        new_username = text.lstrip('@')
        update_user_field(target, 'telegram_username', new_username)
        add_system_log('admin_action', f'تغییر یوزرنیم کاربر {old_user["camelot_name"]}', f'یوزرنیم جدید: @{new_username}', actor_id=user_id, target_id=target)
        await update.message.reply_text(f"✅ یوزرنیم با موفقیت به `@{new_username}` تغییر یافت.", parse_mode='Markdown')
    
    elif field == 'national':
        if len(text) != 6 or not text.isdigit():
            await update.message.reply_text("❌ کد ملی باید ۶ رقم باشد. دوباره وارد کنید:")
            return ADMIN_EDIT_STATE
        # بررسی تکراری نبودن
        existing = get_user_by_national_id(text)
        if existing and existing['telegram_id'] != target:
            await update.message.reply_text("❌ این کد ملی قبلاً به کاربر دیگری تعلق دارد. لطفاً کد دیگری وارد کنید:")
            return ADMIN_EDIT_STATE
        # کد ملی قبلی را آزاد می‌کنیم (با NULL کردن آن) سپس کد جدید را تنظیم می‌کنیم
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE citizens SET national_id = ? WHERE telegram_id = ?", (text, target))
        conn.commit()
        conn.close()
        add_system_log('admin_action', f'تغییر کد ملی کاربر {old_user["camelot_name"]}', f'کد جدید: {text}', actor_id=user_id, target_id=target)
        await update.message.reply_text(f"✅ کد ملی با موفقیت به `{text}` تغییر یافت.", parse_mode='Markdown')
    
    context.user_data.pop('edit_field', None)
    context.user_data.pop('edit_target', None)
    return ConversationHandler.END

# ==================== تغییر نقش ====================
async def admin_change_role(update: Update, context, target_telegram_id):
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
    
    # چرخش نقش: شهروند -> کارمند -> شاه -> شهروند
    roles = ['شهروند', 'کارمند', 'شاه']
    current = user['role']
    try:
        idx = roles.index(current)
        new_role = roles[(idx + 1) % len(roles)]
    except:
        new_role = 'شهروند'
    
    update_user_field(target_telegram_id, 'role', new_role)
    add_system_log('admin_action', f'تغییر نقش کاربر {user["camelot_name"]}', f'نقش جدید: {new_role}', actor_id=user_id, target_id=target_telegram_id)
    await query.edit_message_text(
        f"✅ نقش کاربر با موفقیت به **{new_role}** تغییر یافت.",
        reply_markup=main_menu_keyboard(user_id),
        parse_mode='Markdown'
    )

# ==================== اخراج شهروند ====================
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
        [InlineKeyboardButton("❌ لغو", callback_data=f"admin_cancel_exile")]
    ])
    await query.edit_message_text(
        f"⚠️ **تأیید اخراج شهروند**\n\n"
        f"کاربر: {user['camelot_name']} (نام واقعی: {user['real_name']})\n"
        f"کد ملی فعلی: {user['national_id']}\n\n"
        f"آیا از اخراج این شهروند مطمئن هستید؟\n"
        f"کد ملی او آزاد می‌شود و دیگر نمی‌تواند از این حساب استفاده کند.\n"
        f"(اطلاعات کاربر در دیتابیس باقی می‌ماند)",
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
    add_system_log('admin_action', f'اخراج شهروند {user["camelot_name"]}', f'کد ملی قبلی: {user["national_id"]}', actor_id=user_id, target_id=target)
    await query.edit_message_text(
        f"✅ شهروند {user['camelot_name']} با موفقیت اخراج شد.\nکد ملی {user['national_id']} آزاد شد.",
        reply_markup=main_menu_keyboard(user_id),
        parse_mode='Markdown'
    )

async def admin_cancel_exile(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await query.edit_message_text("⛔ دسترسی ندارید.")
        return
    await query.edit_message_text("❌ اخراج لغو شد.", reply_markup=main_menu_keyboard(user_id))

# ==================== ارسال پیام همگانی ====================
async def admin_broadcast_start(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
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
    if user_id != OWNER_ID:
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

# ==================== لاگ‌های سیستم ====================
LOGS_PER_PAGE = 10

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

# ==================== پشتیبان‌گیری و بازیابی ====================
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
import asyncio

def main():
    init_db()
    if get_config('bot_status') is None:
        set_bot_status('on')
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # ثبت‌نام
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
    
    # مدیریت کاربر با آیدی
    manage_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_manage_user_start, pattern='^admin_manage_user$')],
        states={
            ADMIN_USER_MANAGE_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_manage_user_receive)],
        },
        fallbacks=[CommandHandler('start', start), CommandHandler('cancel', start)],
    )
    app.add_handler(manage_conv)
    
    # ویرایش فیلدها
    edit_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(lambda u,c: admin_edit_field_start(u,c, 'real_name', int(u.callback_query.data.split('_')[3])), pattern='^admin_edit_realname_'),
            CallbackQueryHandler(lambda u,c: admin_edit_field_start(u,c, 'camelot', int(u.callback_query.data.split('_')[3])), pattern='^admin_edit_camelot_'),
            CallbackQueryHandler(lambda u,c: admin_edit_field_start(u,c, 'age', int(u.callback_query.data.split('_')[3])), pattern='^admin_edit_age_'),
            CallbackQueryHandler(lambda u,c: admin_edit_field_start(u,c, 'username', int(u.callback_query.data.split('_')[3])), pattern='^admin_edit_username_'),
            CallbackQueryHandler(lambda u,c: admin_edit_field_start(u,c, 'national', int(u.callback_query.data.split('_')[3])), pattern='^admin_edit_national_'),
        ],
        states={
            ADMIN_EDIT_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit_value)],
        },
        fallbacks=[CommandHandler('start', start), CommandHandler('cancel', start)],
    )
    app.add_handler(edit_conv)
    
    # ارسال پیام همگانی
    broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_broadcast_start, pattern='^admin_broadcast$')],
        states={
            ADMIN_BROADCAST_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_receive)],
        },
        fallbacks=[CommandHandler('start', start), CommandHandler('cancel', start)],
    )
    app.add_handler(broadcast_conv)
    
    # پشتیبان‌گیری - بازیابی
    backup_import_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_backup_import_start, pattern='^admin_backup_import$')],
        states={
            ADMIN_BACKUP_STATE: [MessageHandler(filters.Document.ALL, admin_backup_import_file)],
        },
        fallbacks=[CommandHandler('start', start), CommandHandler('cancel', start)],
    )
    app.add_handler(backup_import_conv)
    
    # کالبک‌های اصلی
    app.add_handler(CallbackQueryHandler(panel_callback, pattern='^panel$'))
    app.add_handler(CallbackQueryHandler(admin_users_list, pattern='^admin_users$'))
    app.add_handler(CallbackQueryHandler(admin_users_page_handler, pattern='^admin_users_page_'))
    app.add_handler(CallbackQueryHandler(admin_logs_list, pattern='^admin_logs$'))
    app.add_handler(CallbackQueryHandler(admin_logs_page_handler, pattern='^admin_logs_page_'))
    app.add_handler(CallbackQueryHandler(admin_backup_menu, pattern='^admin_backup$'))
    app.add_handler(CallbackQueryHandler(admin_backup_export, pattern='^admin_backup_export$'))
    app.add_handler(CallbackQueryHandler(admin_toggle_bot, pattern='^admin_toggle_bot$'))
    app.add_handler(CallbackQueryHandler(back_to_menu, pattern='^back_to_menu$'))
    app.add_handler(CallbackQueryHandler(back_to_menu, pattern='^back_to_panel$'))
    
    app.add_handler(CallbackQueryHandler(balance_callback, pattern='^balance$'))
    app.add_handler(CallbackQueryHandler(my_info_callback, pattern='^my_info$'))
    app.add_handler(CallbackQueryHandler(notifications_callback, pattern='^notifications$'))
    app.add_handler(CallbackQueryHandler(support_callback, pattern='^support$'))
    
    # تغییر نقش و اخراج
    app.add_handler(CallbackQueryHandler(lambda u,c: admin_change_role(u,c, int(u.callback_query.data.split('_')[3])), pattern='^admin_change_role_'))
    app.add_handler(CallbackQueryHandler(lambda u,c: admin_exile_user(u,c, int(u.callback_query.data.split('_')[3])), pattern='^admin_exile_'))
    app.add_handler(CallbackQueryHandler(admin_exile_confirm, pattern='^admin_exile_confirm_'))
    app.add_handler(CallbackQueryHandler(admin_cancel_exile, pattern='^admin_cancel_exile$'))
    
    print("✅ ربات ثبت احوال کملوت با پنل مدیریت کامل راه‌اندازی شد!")
    app.run_polling()

if __name__ == '__main__':
    main()
