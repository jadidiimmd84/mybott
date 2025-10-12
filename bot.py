import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler
import yt_dlp
import os
import sys
import requests
import json
from PIL import Image, ImageDraw, ImageFont
import subprocess
import certifi
import asyncio
import glob
from datetime import datetime, timedelta
from instagrapi import Client
import psutil  # برای مانیتورینگ منابع
import time
import shutil

# تنظیمات فایل‌ها
CHANNELS_FILE = 'channels.json'
STATS_FILE = 'stats.json'
USER_DATA_FILE = 'user_data.json'
FEEDBACK_FILE = 'feedback.json'
MONITORING_FILE = 'monitoring.json'

# تنظیمات لاگینگ
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# توابع مدیریت کانال‌ها
def load_channels():
    if os.path.exists(CHANNELS_FILE):
        with open(CHANNELS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_channels(channels):
    with open(CHANNELS_FILE, 'w', encoding='utf-8') as f:
        json.dump(channels, f, ensure_ascii=False, indent=2)

# بررسی عضویت کاربر در کانال‌ها
async def check_user_membership(user_id, context):
    channels = load_channels()
    if not channels:
        return True, []
    
    not_joined = []
    for channel in channels:
        try:
            member = await context.bot.get_chat_member(chat_id=channel['channel_id'], user_id=user_id)
            if member.status in ['left', 'kicked']:
                not_joined.append(channel)
        except Exception as e:
            logger.error(f"خطا در بررسی عضویت کانال {channel['channel_id']}: {e}")
            continue
    
    return len(not_joined) == 0, not_joined

# ساخت کیبورد کانال‌های عضو نشده
def get_join_channels_keyboard(channels):
    buttons = []
    for channel in channels:
        buttons.append([InlineKeyboardButton(
            f"عضویت در {channel['channel_name']}", 
            url=channel['channel_link']
        )])
    buttons.append([InlineKeyboardButton("✅ عضو شدم", callback_data="check_membership")])
    return InlineKeyboardMarkup(buttons)

# توکن ربات
TOKEN = os.environ.get("TOKEN")

# آیدی ادمین
ADMIN_ID = int(os.environ.get("ADMIN_ID"))

# اطلاعات اکانت اینستاگرام
INSTA_USERNAME = "_.mamaad_"
INSTA_PASSWORD = "M@m13841384"

# دیکشنری سوالات متداول (FAQ)
FAQ = {
    'fa': {
        'instagram': 'برای دانلود از اینستاگرام، لینک پست، ریلز یا استوری را ارسال کنید. مثال: https://www.instagram.com/p/XXXXX',
        'pinterest': 'لینک پین یا برد پینترست را ارسال کنید. مثال: https://pin.it/XXXXX یا https://www.pinterest.com/pin/XXXXX',
        'tiktok': 'لینک ویدیو تیک‌تاک را ارسال کنید. مثال: https://www.tiktok.com/@user/video/XXXXX',
        'problems': 'اگر دانلود انجام نشد، اطمینان حاصل کنید که لینک صحیح است. می‌توانید با /contact_admin با مدیر تماس بگیرید.',
        'quality': 'برای ویدیوها، پس از ارسال لینک می‌توانید کیفیت (مانند 720p یا 1080p) را انتخاب کنید.',
    },
    'en': {
        'instagram': 'To download from Instagram, send the link of a post, reel, or story. Example: https://www.instagram.com/p/XXXXX',
        'pinterest': 'Send the Pinterest pin or board link. Example: https://pin.it/XXXXX or https://www.pinterest.com/pin/XXXXX',
        'tiktok': 'Send the TikTok video link. Example: https://www.tiktok.com/@user/video/XXXXX',
        'problems': 'If the download fails, ensure the link is correct. You can contact the admin with /contact_admin.',
        'quality': 'For videos, you can choose the quality (like 720p or 1080p) after sending the link.',
    }
}

# پیام‌ها برای زبان‌های مختلف
MESSAGES = {
    'fa': {
        'start': 'سلام! من یک ربات دانلودکننده هستم. لطفاً یک لینک ارسال کنید تا برایتان دانلود کنم.',
        'help': 'برای شروع کار، کافی است یکی از دکمه‌های زیر را فشار دهید:\n\n* **شروع دانلود**: یک لینک از اینستاگرام (پست، ریلز، استوری)، توییتر/X، SoundCloud، تیک‌تاک یا پینترست ارسال کنید تا برایتان دانلود کنم.\n* **راهنما**: این راهنمایی را که در حال خواندن آن هستید، دوباره نمایش می‌دهد.\n* **تغییر زبان**: اگر مایل به گفتگو به زبان انگلیسی هستید، این دکمه را فشار دهید.\n* **انتقادات و پیشنهادات**: نظر یا پیشنهاد خود را ارسال کنید.\n* **ارتباط با مدیر**: مستقیماً با مدیر ارتباط برقرار کنید.\n* **سوالات متداول**: پاسخ به سؤالات رایج در مورد دانلود و استفاده از ربات.',
        'select_lang': 'لطفاً زبان خود را انتخاب کنید:',
        'lang_set': 'زبان شما به فارسی تغییر یافت.',
        'processing': 'لینک دریافت شد، در حال پردازش...',
        'downloaded': 'دانلود تکمیل شد.',
        'error': 'متأسفانه مشکلی پیش آمده: {}',
        'help_btn': 'راهنما',
        'change_lang_btn': 'تغییر زبان',
        'download_prompt_btn': 'شروع دانلود',
        'user_account_btn': 'حساب کاربری',
        'feedback_btn': 'انتقادات و پیشنهادات',
        'contact_admin_btn': 'ارتباط با مدیر',
        'faq_btn': 'سوالات متداول',
        'faq_prompt': 'سؤال خود را مطرح کنید:',
        'download_prompt': 'لطفاً لینک مورد نظر را ارسال کنید:',
        'type_choice': 'چه چیزی را می‌خواهید دانلود کنید؟',
        'watermark_choice': 'با واترمارک یا بدون واترمارک؟',
        'user_stats': '📊 **آمار حساب کاربری شما**\n\nتعداد کل دانلودها: {}\nنوع دانلودها:\n  - ویدیو: {}\n  - صدا: {}\n  - عکس: {}\n\nزبان فعلی: {}',
        'notification_sent': '✅ اطلاعیه با موفقیت به {} کاربر ارسال شد.\n❌ {} کاربر دریافت نکردند (احتمالاً ربات را بلاک کرده‌اند).',
        'notification_usage': 'برای ارسال اطلاعیه از این فرمت استفاده کنید:\n/notify پیام شما اینجا',
        'admin_only': 'این دستور فقط برای مدیر است.',
        'notification_received': '📢 **اطلاعیه مدیریت**\n\n{}',
        'feedback_prompt': 'لطفاً انتقاد یا پیشنهاد خود را بنویسید:',
        'feedback_received': '✅ نظر شما با موفقیت ثبت شد و برای مدیر ارسال خواهد شد.',
        'contact_admin_prompt': 'پیام خود را برای مدیر بنویسید:',
        'contact_admin_received': '✅ پیام شما برای مدیر ارسال شد.',
        'feedback_to_admin': '📬 **انتقاد یا پیشنهاد جدید**\nاز: {}\nمتن: {}\nزمان: {}\nکاربر آیدی: {}',
        'message_to_admin': '📬 **پیام جدید برای مدیر**\nاز: {}\nمتن: {}\nزمان: {}\nکاربر آیدی: {}',
        'admin_reply_received': '📩 **پاسخ از مدیر**\n\n{}',
        'admin_reply_prompt': 'لطفاً پاسخ خود را برای کاربر با آیدی {} بنویسید:',
        'story_processing': '📲 در حال دریافت استوری، صبر کنید...',
        'story_downloaded': '✅ استوری با موفقیت دانلود شد.',
        'join_required': '❌ برای استفاده از ربات باید در کانال‌های زیر عضو شوید:',
        'join_check_success': '✅ عضویت شما تأیید شد! اکنون می‌توانید از ربات استفاده کنید.',
        'join_check_failed': '❌ هنوز در همه کانال‌ها عضو نشده‌اید. لطفاً ابتدا عضو شوید.',
        'admin_panel': '⚙️ پنل مدیریت',
        'channel_management': '📢 مدیریت کانال‌های عضویت اجباری',
        'add_channel': '➕ افزودن کانال',
        'remove_channel': '➖ حذف کانال',
        'list_channels': '📋 لیست کانال‌ها',
        'channel_list_empty': 'هیچ کانالی ثبت نشده است.',
        'channel_added': '✅ کانال با موفقیت اضافه شد.',
        'channel_removed': '✅ کانال با موفقیت حذف شد.',
        'send_channel_info': 'لطفاً اطلاعات کانال را به این فرمت ارسال کنید:\n\nنام کانال\n@channel_username\nhttps://t.me/channel_username',
        'invalid_channel_format': '❌ فرمت نادرست! لطفاً به فرمت زیر ارسال کنید:\n\nنام کانال\n@channel_username\nhttps://t.me/channel_username',
        'back_to_main': '🔙 بازگشت به منوی اصلی',
        'monitoring': '🔍 مانیتورینگ عملکرد',
        'operation_cancelled': 'عملیات لغو شد.',
        'youtube_not_supported': 'دانلود از یوتیوب پشتیبانی نمی‌شود. لطفاً لینک از پلتفرم‌های دیگر ارسال کنید.'
    },
    'en': {
        'start': 'Hello! I am a downloader bot. Please send a link for me to download.',
        'help': 'To get started, simply press one of the buttons below:\n\n* **Start Download**: Send a link from Instagram (post, reel, story), Twitter/X, SoundCloud, TikTok, or Pinterest for download.\n* **Help**: This will display the guide you are currently reading again.\n* **Change Language**: If you prefer to communicate in English, press this button.\n* **Feedback**: Send your feedback or suggestions.\n* **Contact Admin**: Communicate directly with the admin.\n* **FAQ**: Answers to common questions about downloading and using the bot.',
        'select_lang': 'Please select your language:',
        'lang_set': 'Your language has been set to English.',
        'processing': 'Link received, processing...',
        'downloaded': 'Download completed.',
        'error': 'Unfortunately, an issue has occurred: {}',
        'help_btn': 'Help',
        'change_lang_btn': 'Change Language',
        'download_prompt_btn': 'Start Download',
        'user_account_btn': 'User Account',
        'feedback_btn': 'Feedback',
        'contact_admin_btn': 'Contact Admin',
        'faq_btn': 'FAQ',
        'faq_prompt': 'Please ask your question:',
        'download_prompt': 'Please send the desired link:',
        'type_choice': 'What would you like to download?',
        'watermark_choice': 'With or without watermark?',
        'user_stats': '📊 **Your Account Statistics**\n\nTotal downloads: {}\nDownload types:\n  - Video: {}\n  - Audio: {}\n  - Image: {}\n\nCurrent language: {}',
        'notification_sent': '✅ Notification successfully sent to {} users.\n❌ {} users did not receive it (likely blocked the bot).',
        'notification_usage': 'To send a notification, use this format:\n/notify Your message here',
        'admin_only': 'This command is only for the admin.',
        'notification_received': '📢 **Admin Notification**\n\n{}',
        'feedback_prompt': 'Please write your feedback or suggestion:',
        'feedback_received': '✅ Your feedback has been recorded and will be sent to the admin.',
        'contact_admin_prompt': 'Write your message for the admin:',
        'contact_admin_received': '✅ Your message has been sent to the admin.',
        'feedback_to_admin': '📬 **New Feedback**\nFrom: {}\nMessage: {}\nTime: {}\nUser ID: {}',
        'message_to_admin': '📬 **New Message for Admin**\nFrom: {}\nMessage: {}\nTime: {}\nUser ID: {}',
        'admin_reply_received': '📩 **Reply from Admin**\n\n{}',
        'admin_reply_prompt': 'Please write your reply to the user with ID {}:',
        'monitoring': '🔍 Performance Monitoring',
        'operation_cancelled': 'Operation cancelled.',
        'youtube_not_supported': 'YouTube download is not supported. Please send a link from other platforms.'
    }
}

# کیبورد انتخاب زبان
LANG_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton("فارسی"), KeyboardButton("English")]],
    resize_keyboard=True,
    one_time_keyboard=True
)

# تابع ساخت کیبورد اصلی بر اساس زبان
def get_main_keyboard(lang):
    if lang == 'fa':
        return ReplyKeyboardMarkup(
            [[KeyboardButton(MESSAGES['fa']['download_prompt_btn'])],
             [KeyboardButton(MESSAGES['fa']['user_account_btn']), KeyboardButton(MESSAGES['fa']['help_btn']), KeyboardButton(MESSAGES['fa']['change_lang_btn'])],
             [KeyboardButton(MESSAGES['fa']['feedback_btn']), KeyboardButton(MESSAGES['fa']['contact_admin_btn']), KeyboardButton(MESSAGES['fa']['faq_btn'])]],
            resize_keyboard=True,
            one_time_keyboard=False
        )
    else:
        return ReplyKeyboardMarkup(
            [[KeyboardButton(MESSAGES['en']['download_prompt_btn'])],
             [KeyboardButton(MESSAGES['en']['user_account_btn']), KeyboardButton(MESSAGES['en']['help_btn']), KeyboardButton(MESSAGES['en']['change_lang_btn'])],
             [KeyboardButton(MESSAGES['en']['feedback_btn']), KeyboardButton(MESSAGES['en']['contact_admin_btn']), KeyboardButton(MESSAGES['en']['faq_btn'])]],
            resize_keyboard=True,
            one_time_keyboard=False
        )

# تابع برای دریافت کیبورد سوالات متداول
def get_faq_keyboard(lang):
    buttons = [
        [InlineKeyboardButton("دانلود از اینستاگرام" if lang == 'fa' else "Download from Instagram", callback_data="faq_instagram")],
        [InlineKeyboardButton("دانلود از تیک‌تاک" if lang == 'fa' else "Download from TikTok", callback_data="faq_tiktok")],
        [InlineKeyboardButton("دانلود از پینترست" if lang == 'fa' else "Download from Pinterest", callback_data="faq_pinterest")],
        [InlineKeyboardButton("مشکلات دانلود" if lang == 'fa' else "Download Problems", callback_data="faq_problems")],
        [InlineKeyboardButton("انتخاب کیفیت" if lang == 'fa' else "Choose Quality", callback_data="faq_quality")]
    ]
    return InlineKeyboardMarkup(buttons)

# تابع برای دریافت کیبورد بازگشت به FAQ
def get_faq_back_keyboard(lang):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("بازگشت به سوالات" if lang == 'fa' else "Back to FAQ", callback_data="faq_back")]
    ])

# تابع برای بارگذاری آمار
def load_stats():
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'users': {}, 'downloads': 0}

# تابع برای ذخیره آمار
def save_stats(stats):
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

# تابع برای بارگذاری داده‌های مانیتورینگ
def load_monitoring_data():
    if os.path.exists(MONITORING_FILE):
        with open(MONITORING_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        'successful_downloads': 0,
        'failed_downloads': 0,
        'response_times': [],
        'errors': [],
        'blocked_users': []
    }

# تابع برای ذخیره داده‌های مانیتورینگ
def save_monitoring_data(data):
    with open(MONITORING_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# تابع برای ثبت داده‌های مانیتورینگ
def log_monitoring_data(success=True, response_time=None, error=None, user_id=None):
    data = load_monitoring_data()
    
    if success:
        data['successful_downloads'] += 1
    else:
        data['failed_downloads'] += 1
    
    if response_time is not None:
        data['response_times'].append(response_time)
        if len(data['response_times']) > 100:  # محدود کردن به ۱۰۰ مورد آخر
            data['response_times'] = data['response_times'][-100:]
    
    if error is not None:
        data['errors'].append({
            'timestamp': datetime.now().isoformat(),
            'error': str(error),
            'user_id': user_id
        })
        if len(data['errors']) > 20:  # محدود کردن به ۲۰ خطای آخر
            data['errors'] = data['errors'][-20:]
    
    if user_id and user_id not in data['blocked_users']:
        data['blocked_users'].append(user_id)
        if len(data['blocked_users']) > 100:  # محدود کردن به ۱۰۰ کاربر
            data['blocked_users'] = data['blocked_users'][-100:]
    
    save_monitoring_data(data)

# تابع برای دریافت گزارش مانیتورینگ
def get_monitoring_report():
    monitoring_data = load_monitoring_data()
    stats = load_stats()
    
    total_downloads = monitoring_data['successful_downloads'] + monitoring_data['failed_downloads']
    success_rate = (monitoring_data['successful_downloads'] / total_downloads * 100) if total_downloads > 0 else 0
    avg_response_time = sum(monitoring_data['response_times']) / len(monitoring_data['response_times']) if monitoring_data['response_times'] else 0
    
    # مانیتورینگ منابع سیستم
    try:
        cpu_usage = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        memory_usage = memory.percent
    except Exception as e:
        cpu_usage = "نامشخص"
        memory_usage = "نامشخص"
        logger.error(f"خطا در دریافت منابع سیستم: {e}")
    
    errors = monitoring_data['errors'][-5:]  # فقط ۵ خطای آخر
    blocked_users_count = len(set(monitoring_data['blocked_users']))
    
    return {
        'success_rate': round(success_rate, 2),
        'total_downloads': total_downloads,
        'successful_downloads': monitoring_data['successful_downloads'],
        'failed_downloads': monitoring_data['failed_downloads'],
        'avg_response_time': round(avg_response_time, 2),
        'cpu_usage': cpu_usage,
        'memory_usage': memory_usage,
        'recent_errors': errors,
        'blocked_users_count': blocked_users_count
    }

# تابع برای بارگذاری اطلاعات کاربران
def load_user_data():
    if os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return {int(k): v for k, v in data.items()}
    return {}

# تابع برای ذخیره اطلاعات کاربران
def save_user_data(data):
    str_keys_data = {str(k): v for k, v in data.items()}
    with open(USER_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(str_keys_data, f, ensure_ascii=False, indent=2)

# تابع برای بارگذاری انتقادات و پیشنهادات
def load_feedback():
    if os.path.exists(FEEDBACK_FILE):
        with open(FEEDBACK_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

# تابع برای ذخیره Criticism and suggestions
def save_feedback(feedback):
    with open(FEEDBACK_FILE, 'w', encoding='utf-8') as f:
        json.dump(feedback, f, ensure_ascii=False, indent=2)

bot_stats = load_stats()
user_data = load_user_data()

# تابع /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_info = update.effective_user
    username = user_info.username if user_info.username else ""
    first_name = user_info.first_name if user_info.first_name else ""
    last_name = user_info.last_name if user_info.last_name else ""
    
    global user_data, bot_stats
    user_data = load_user_data()
    bot_stats = load_stats()

    # ریست وضعیت awaiting برای ادمین اگر لازم باشد
    if user_id == ADMIN_ID:
        context.user_data.pop('awaiting_channel_info', None)

    # ثبت اطلاعات کاربر
    if str(user_id) not in bot_stats['users']:
        bot_stats['users'][str(user_id)] = {
            'lang': 'fa',
            'username': username,
            'first_name': first_name,
            'last_name': last_name,
            'last_seen': datetime.now().isoformat()
        }
        save_stats(bot_stats)
    
    # بررسی عضویت (اگر ادمین نیست)
    if user_id != ADMIN_ID:
        is_member, not_joined_channels = await check_user_membership(user_id, context)
        if not is_member:
            await update.message.reply_text(
                MESSAGES['fa']['join_required'],
                reply_markup=get_join_channels_keyboard(not_joined_channels)
            )
            return
    
    # ادامه کد start معمولی...
    if user_id not in user_data:
        user_data[user_id] = {'lang': 'fa', 'add_watermark': True, 'download_history': []}
        save_user_data(user_data)
        await update.message.reply_text(
            MESSAGES['fa']['select_lang'],
            reply_markup=LANG_KEYBOARD
        )
    else:
        if 'download_history' not in user_data[user_id]:
            user_data[user_id]['download_history'] = []
            save_user_data(user_data)
        await update.message.reply_text(
            MESSAGES['fa']['select_lang'],
            reply_markup=LANG_KEYBOARD
        )

# تابع ارسال نوتیفیکیشن به همه کاربران
async def notify_all_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text(MESSAGES['fa']['admin_only'])
        return
    
    if not context.args:
        await update.message.reply_text(MESSAGES['fa']['notification_usage'])
        return
    
    notification_text = ' '.join(context.args)
    
    global bot_stats
    bot_stats = load_stats()
    
    success_count = 0
    failed_count = 0
    
    for user_id_str in bot_stats['users'].keys():
        try:
            target_user_id = int(user_id_str)
            user_lang = bot_stats['users'][user_id_str].get('lang', 'fa')
            
            final_message = MESSAGES[user_lang]['notification_received'].format(notification_text)
            
            await context.bot.send_message(
                chat_id=target_user_id,
                text=final_message,
                parse_mode='Markdown'
            )
            success_count += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            failed_count += 1
            log_monitoring_data(success=False, error=f"Failed to send notification: {e}", user_id=int(user_id_str))
            logger.error(f"خطا در ارسال پیام به کاربر {user_id_str}: {e}")
    
    result_message = MESSAGES['fa']['notification_sent'].format(success_count, failed_count)
    await update.message.reply_text(result_message)

# تابع برای تغییر زبان
async def change_language_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = user_data.get(user_id, {}).get('lang', 'fa')
    await update.message.reply_text(
        MESSAGES[lang]['select_lang'],
        reply_markup=LANG_KEYBOARD
    )

# تابع برای تنظیم زبان
async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    global user_data
    user_data = load_user_data()
    text = update.message.text
    if text == "فارسی":
        user_data[user_id] = user_data.get(user_id, {'add_watermark': True, 'download_history': []})
        user_data[user_id]['lang'] = 'fa'
        save_user_data(user_data)
        await update.message.reply_text(MESSAGES['fa']['lang_set'], reply_markup=get_main_keyboard('fa'))
    elif text == "English":
        user_data[user_id] = user_data.get(user_id, {'add_watermark': True, 'download_history': []})
        user_data[user_id]['lang'] = 'en'
        save_user_data(user_data)
        await update.message.reply_text(MESSAGES['en']['lang_set'], reply_markup=get_main_keyboard('en'))

# تابع راهنما
async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = user_data.get(user_id, {}).get('lang', 'fa')
    await update.message.reply_text(MESSAGES[lang]['help'])

# تابع برای سوالات متداول
async def faq_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = user_data.get(user_id, {}).get('lang', 'fa')
    await update.message.reply_text(
        MESSAGES[lang]['faq_prompt'],
        reply_markup=get_faq_keyboard(lang)
    )

# هندلر برای مدیریت کلیک روی دکمه‌های FAQ
async def handle_faq_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    lang = user_data.get(user_id, {}).get('lang', 'fa')
    
    if query.data == 'faq_back':
        await query.edit_message_text(
            text=MESSAGES[lang]['faq_prompt'],
            reply_markup=get_faq_keyboard(lang)
        )
        return
    
    faq_key = query.data.replace('faq_', '')
    
    if faq_key in FAQ[lang]:
        await query.edit_message_text(
            text=FAQ[lang][faq_key],
            reply_markup=get_faq_back_keyboard(lang)
        )
        await query.message.reply_text(
            text=MESSAGES[lang]['start'],
            reply_markup=get_main_keyboard(lang)
        )
    else:
        await query.edit_message_text(
            text=MESSAGES[lang]['error'].format("موضوع مورد نظر یافت نشد."),
            reply_markup=get_faq_back_keyboard(lang)
        )
        await query.message.reply_text(
            text=MESSAGES[lang]['start'],
            reply_markup=get_main_keyboard(lang)
        )

# تابع درخواست لینک از کاربر
async def download_prompt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = user_data.get(user_id, {}).get('lang', 'fa')
    await update.message.reply_text(MESSAGES[lang]['download_prompt'])

# تابع برای درخواست انتقادات و پیشنهادات
async def feedback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = user_data.get(user_id, {}).get('lang', 'fa')
    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="cancel_feedback")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(MESSAGES[lang]['feedback_prompt'], reply_markup=reply_markup)
    context.user_data['awaiting_feedback'] = True

# تابع برای درخواست ارتباط با ادمین
async def contact_admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = user_data.get(user_id, {}).get('lang', 'fa')
    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="cancel_contact")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(MESSAGES[lang]['contact_admin_prompt'], reply_markup=reply_markup)
    context.user_data['awaiting_admin_message'] = True

# تابع برای دریافت و پردازش انتقادات و پیشنهادات
async def handle_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = user_data.get(user_id, {}).get('lang', 'fa')
    
    if context.user_data.get('awaiting_feedback', False):
        feedback_text = update.message.text
        feedback = load_feedback()
        
        user_info = bot_stats['users'].get(str(user_id), {})
        username = user_info.get('username', 'Unknown')
        timestamp = datetime.now().isoformat()
        
        feedback.append({
            'user_id': user_id,
            'username': username,
            'text': feedback_text,
            'timestamp': timestamp
        })
        save_feedback(feedback)
        
        reply_keybo...(truncated 25032 characters)... message_id=sent_message_id,
                    text=MESSAGES[lang]['error'].format("لینک محدود شده است (403). لطفاً VPN استفاده کنید یا لینک دیگری امتحان کنید.")
                )
        else:
            response_time = time.time() - start_time
            log_monitoring_data(success=False, response_time=response_time, error=str(e), user_id=user_id)
            await context.bot.edit_message_text(
                chat_id=user_id,
                message_id=sent_message_id,
                text=MESSAGES[lang]['error'].format(f"خطای دانلود: {e}")
            )
    except yt_dlp.utils.ExtractorError as e:
        response_time = time.time() - start_time
        error_msg = str(e).lower()
        if "no video formats found" in error_msg:
            log_monitoring_data(success=False, response_time=response_time, error=str(e), user_id=user_id)
            await context.bot.edit_message_text(
                chat_id=user_id,
                message_id=sent_message_id,
                text="🔄 در حال تشخیص عکس... تلاش مجدد"
            )
            
            context.job_queue.run_once(
                process_download,
                when=2,
                data={
                    'user_id': user_id,
                    'download_url': user_url,
                    'add_watermark': add_watermark,
                    'is_audio_only': False,
                    'is_image_only': True,
                    'message_id': sent_message_id
                }
            )
            return
        else:
            log_monitoring_data(success=False, response_time=response_time, error=str(e), user_id=user_id)
            await context.bot.edit_message_text(
                chat_id=user_id,
                message_id=sent_message_id,
                text=MESSAGES[lang]['error'].format(f"خطای دانلود: {e}")
            )

    except Exception as e:
        response_time = time.time() - start_time
        log_monitoring_data(success=False, response_time=response_time, error=str(e), user_id=user_id)
        logger.error(f"خطای کلی: {e}")
        await context.bot.edit_message_text(
            chat_id=user_id,
            message_id=sent_message_id,
            text=MESSAGES[lang]['error'].format(str(e))
        )
        await context.bot.send_message(chat_id=user_id, text=MESSAGES[lang]['start'], reply_markup=get_main_keyboard(lang))

    finally:
        for file in file_names:
            if os.path.exists(file):
                try:
                    os.remove(file)
                except:
                    pass

# هندلر برای دریافت لینک و نمایش دکمه‌های نوع دانلود
async def handle_download_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = user_data.get(user_id, {}).get('lang', 'fa')
    
    url = update.message.text
    context.user_data['download_url'] = url
    
    # Check for YouTube URLs and block them
    if 'youtube.com' in url.lower() or 'youtu.be' in url.lower():
        await update.message.reply_text(MESSAGES[lang]['youtube_not_supported'])
        return
    
    checking_message = await update.message.reply_text("🔍 در حال بررسی نوع محتوا...")
    
    quick_type = quick_url_detection(url)
    
    if 'twitter.com' in url.lower() or 'x.com' in url.lower():
        if '/photo/' in url.lower() or '/media/' in url.lower():
            context.user_data['is_audio_only'] = False
            context.user_data['is_image_only'] = True
            sent_message = await checking_message.edit_text(MESSAGES[lang]['processing'])
            
            context.job_queue.run_once(
                process_download,
                when=0,
                data={
                    'user_id': user_id,
                    'download_url': url,
                    'add_watermark': False,
                    'is_audio_only': False,
                    'is_image_only': True,
                    'message_id': sent_message.message_id
                }
            )
            return
    
    content_info = detect_content_type(url)
    
    await context.bot.delete_message(chat_id=user_id, message_id=checking_message.message_id)
    
    if content_info['is_image']:
        context.user_data['is_audio_only'] = False
        context.user_data['is_image_only'] = True
        sent_message = await update.message.reply_text(MESSAGES[lang]['processing'])
        
        context.job_queue.run_once(
            process_download,
            when=0,
            data={
                'user_id': user_id,
                'download_url': url,
                'add_watermark': False,
                'is_audio_only': False,
                'is_image_only': True,
                'message_id': sent_message.message_id
            }
        )
        return
    
    if content_info['has_video']:
        context.user_data['is_image_only'] = False
        keyboard = [
            [InlineKeyboardButton("ویدیو", callback_data="type_video"),
             InlineKeyboardButton("فقط صدا (MP3)", callback_data="type_audio")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(MESSAGES[lang]['type_choice'], reply_markup=reply_markup)
        return
    
    if content_info['has_audio'] and not content_info['has_video']:
        context.user_data['is_audio_only'] = True
        context.user_data['is_image_only'] = False
        sent_message = await update.message.reply_text(MESSAGES[lang]['processing'])
        
        context.job_queue.run_once(
            process_download,
            when=0,
            data={
                'user_id': user_id,
                'download_url': url,
                'add_watermark': False,
                'is_audio_only': True,
                'is_image_only': False,
                'message_id': sent_message.message_id
            }
        )
        return
    
    await update.message.reply_text(MESSAGES[lang]['error'].format("نوع محتوا قابل تشخیص نیست."))

# هندلر برای مدیریت انتخاب نوع فایل (ویدیو یا صدا)
async def handle_type_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    lang = user_data.get(user_id, {}).get('lang', 'fa')

    if query.data == 'type_video':
        context.user_data['is_audio_only'] = False
        # مستقیم به watermark_choice برو
        keyboard = [
            [InlineKeyboardButton("با واترمارک", callback_data="watermark_on"),
             InlineKeyboardButton("بدون واترمارک", callback_data="watermark_off")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(MESSAGES[lang]['watermark_choice'], reply_markup=reply_markup)
    
    elif query.data == 'type_audio':
        context.user_data['is_audio_only'] = True
        context.user_data['add_watermark'] = False

        sent_message = await query.edit_message_text(MESSAGES[lang]['processing'])
        
        context.job_queue.run_once(
            process_download,
            when=0,
            data={
                'user_id': user_id,
                'download_url': context.user_data['download_url'],
                'add_watermark': False,
                'is_audio_only': True,
                'is_image_only': False,
                'message_id': sent_message.message_id
            }
        )

# هندلر برای مدیریت کلیک روی دکمه‌های واترمارک
async def handle_watermark_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    await query.answer()

    if 'download_url' not in context.user_data:
        await query.edit_message_text("لینک یافت نشد. لطفاً مجدداً لینک را ارسال کنید.")
        return

    add_watermark_choice = (query.data == 'watermark_on')
    
    context.user_data['add_watermark'] = add_watermark_choice
    
    is_audio_only = context.user_data.get('is_audio_only', False)
    is_image_only = context.user_data.get('is_image_only', False)

    sent_message = await query.edit_message_text(MESSAGES[user_data.get(user_id, {}).get('lang', 'fa')]['processing'])

    context.job_queue.run_once(
        process_download,
        when=0,
        data={
            'user_id': user_id,
            'download_url': context.user_data['download_url'],
            'add_watermark': add_watermark_choice,
            'is_audio_only': is_audio_only,
            'is_image_only': is_image_only,
            'message_id': sent_message.message_id
        }
    )

# تابع نمایش آمار حساب کاربری
async def user_account_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    global user_data
    user_data = load_user_data()

    user_info = user_data.get(user_id, {})
    lang = user_info.get('lang', 'fa')
    
    download_history = user_info.get('download_history', [])
    
    total_downloads = len(download_history)
    video_count = sum(1 for item in download_history if item['type'] == 'video')
    audio_count = sum(1 for item in download_history if item['type'] == 'audio')
    image_count = sum(1 for item in download_history if item['type'] == 'image')

    message_text = MESSAGES[lang]['user_stats'].format(
        total_downloads,
        video_count,
        audio_count,
        image_count,
        "فارسی" if lang == 'fa' else "English"
    )
    
    await update.message.reply_text(message_text, parse_mode='Markdown')

# هندلر برای دکمه "عضو شدم"
async def handle_membership_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    lang = user_data.get(user_id, {}).get('lang', 'fa')
    
    is_member, not_joined_channels = await check_user_membership(user_id, context)
    
    if is_member:
        await query.edit_message_text(
            MESSAGES[lang]['join_check_success'],
            reply_markup=None
        )
        await context.bot.send_message(
            chat_id=user_id,
            text=MESSAGES[lang]['start'],
            reply_markup=get_main_keyboard(lang)
        )
    else:
        await query.edit_message_text(
            MESSAGES[lang]['join_check_failed'],
            reply_markup=get_join_channels_keyboard(not_joined_channels)
        )

# هندلر پنل مدیریت (فقط برای ادمین)
async def admin_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text(MESSAGES['fa']['admin_only'])
        return
    
    keyboard = [
        [InlineKeyboardButton("📢 مدیریت کانال‌ها", callback_data="manage_channels")],
        [InlineKeyboardButton("📊 آمار ربات", callback_data="bot_stats")],
        [InlineKeyboardButton("🔍 مانیتورینگ عملکرد", callback_data="monitoring")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]
    ]
    
    await update.message.reply_text(
        "⚙️ پنل مدیریت ربات",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# هندلر مدیریت کانال‌ها، آمار و مانیتورینگ
async def handle_channel_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if user_id != ADMIN_ID:
        await query.edit_message_text("این بخش فقط برای مدیر است.")
        return
    
    if query.data == "manage_channels":
        keyboard = [
            [InlineKeyboardButton("➕ افزودن کانال", callback_data="add_channel")],
            [InlineKeyboardButton("📋 لیست کانال‌ها", callback_data="list_channels")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin")]
        ]
        await query.edit_message_text(
            "📢 مدیریت کانال‌های عضویت اجباری",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == "back_to_manage_channels":
        context.user_data.pop('awaiting_channel_info', None)  # ریست awaiting_channel_info هنگام بازگشت
        keyboard = [
            [InlineKeyboardButton("➕ افزودن کانال", callback_data="add_channel")],
            [InlineKeyboardButton("📋 لیست کانال‌ها", callback_data="list_channels")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin")]
        ]
        await query.edit_message_text(
            "📢 مدیریت کانال‌های عضویت اجباری",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == "bot_stats":
        stats = get_advanced_stats()
        text = f"""📊 **آمار پیشرفته ربات** (به‌روزرسانی: {datetime.now().strftime('%Y/%m/%d %H:%M')})

**آمار کلی:**
- تعداد کاربران کل: {stats['total_users']}
- دانلودهای کل: {stats['total_downloads']}
- کاربران فعال (۳۰ روز اخیر): {stats['active_users']}
- دانلودهای اخیر (۷ روز): {stats['recent_downloads']}

**توزیع دانلودها:**
| نوع | تعداد |
|-----|--------|
| ویدیو | {stats['video_downloads']} |
| صدا | {stats['audio_downloads']} |
| عکس | {stats['image_downloads']} |

**سایر آمار:**
- تعداد فیدبک‌ها: {stats['total_feedback']}
- کانال‌های عضویت: {stats['total_channels']}"""
        
        keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin")]]
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    elif query.data == "monitoring":  # مانیتورینگ عملکرد
        report = get_monitoring_report()
        text = f"""🔍 **مانیتورینگ عملکرد ربات** (به‌روزرسانی: {datetime.now().strftime('%Y/%m/%d %H:%M')})

**عملکرد دانلود:**
- کل درخواست‌های دانلود: {report['total_downloads']}
- دانلودهای موفق: {report['successful_downloads']}
- دانلودهای ناموفق: {report['failed_downloads']}
- نرخ موفقیت: {report['success_rate']}% 

**زمان پاسخ:**
- میانگین زمان پاسخ: {report['avg_response_time']} ثانیه

**منابع سیستم:**
- مصرف CPU: {report['cpu_usage']}%
- مصرف حافظه: {report['memory_usage'] }%

**کاربران بلاک‌کننده:**
- تعداد کاربران بلاک‌کننده: {report['blocked_users_count']}

**خطاهای اخیر:**
"""
        for error in report['recent_errors']:
            text += f"- {error['timestamp']}: {error['error']} (کاربر: {error['user_id']})\n"
        
        if not report['recent_errors']:
            text += "- هیچ خطایی ثبت نشده است.\n"
        
        keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_admin")]]
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    elif query.data == "add_channel":
        keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_manage_channels")]]
        await query.edit_message_text(
            MESSAGES['fa']['send_channel_info'],
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        context.user_data['awaiting_channel_info'] = True
    
    elif query.data == "list_channels":
        channels = load_channels()
        if not channels:
            await query.edit_message_text(
                MESSAGES['fa']['channel_list_empty'],
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="manage_channels")]])
            )
        else:
            text = "📋 لیست کانال‌های عضویت اجباری:\n\n"
            buttons = []
            for i, channel in enumerate(channels, 1):
                text += f"{i}. {channel['channel_name']}\n"
                text += f"    ID: {channel['channel_id']}\n"
                text += f"    لینک: {channel['channel_link']}\n\n"
                buttons.append([InlineKeyboardButton(
                    f"❌ حذف {channel['channel_name']}", 
                    callback_data=f"remove_channel_{i-1}"
                )])
            
            buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="manage_channels")])
            
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
    
    elif query.data.startswith("remove_channel_"):
        index = int(query.data.split("_")[2])
        channels = load_channels()
        if 0 <= index < len(channels):
            removed = channels.pop(index)
            save_channels(channels)
            await query.edit_message_text(
                f"✅ کانال {removed['channel_name']} حذف شد.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="list_channels")]])
            )
    
    elif query.data == "back_to_admin":
        keyboard = [
            [InlineKeyboardButton("📢 مدیریت کانال‌ها", callback_data="manage_channels")],
            [InlineKeyboardButton("📊 آمار ربات", callback_data="bot_stats")],
            [InlineKeyboardButton("🔍 مانیتورینگ عملکرد", callback_data="monitoring")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]
        ]
        await query.edit_message_text(
            "⚙️ پنل مدیریت ربات",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == "back_to_main":
        await query.edit_message_text(MESSAGES['fa']['back_to_main'])

# هندلر دریافت اطلاعات کانال
async def handle_channel_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID or not context.user_data.get('awaiting_channel_info'):
        return
    
    text = update.message.text.strip()
    lines = text.split('\n')
    
    if len(lines) < 3:
        keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_manage_channels")]]
        await update.message.reply_text(MESSAGES['fa']['invalid_channel_format'], reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    channel_name = lines[0].strip()
    channel_username = lines[1].strip()
    channel_link = lines[2].strip()
    
    if channel_username.startswith('@'):
        channel_id = channel_username
    else:
        channel_id = f"@{channel_username}"
    
    channels = load_channels()
    channels.append({
        'channel_name': channel_name,
        'channel_id': channel_id,
        'channel_link': channel_link
    })
    save_channels(channels)
    
    await update.message.reply_text(
        MESSAGES['fa']['channel_added'],
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به مدیریت کانال‌ها", callback_data="manage_channels")]])
    )
    
    context.user_data['awaiting_channel_info'] = False

# هندلر برای لغو عملیات (بازگشت)
async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    lang = user_data.get(user_id, {}).get('lang', 'fa')
    
    if query.data == 'cancel_feedback':
        context.user_data['awaiting_feedback'] = False
    elif query.data == 'cancel_contact':
        context.user_data['awaiting_admin_message'] = False
    
    await query.edit_message_text(MESSAGES[lang]['operation_cancelled'])
    await context.bot.send_message(
        chat_id=user_id,
        text=MESSAGES[lang]['start'],
        reply_markup=get_main_keyboard(lang)
    )

# تابع برای محاسبه آمار پیشرفته (برای ادغام با مانیتورینگ)
def get_advanced_stats():
    global bot_stats, user_data
    bot_stats = load_stats()
    user_data = load_user_data()
    feedback = load_feedback()
    channels = load_channels()
    
    total_users = len(bot_stats['users'])
    total_downloads = bot_stats['downloads']
    
    video_downloads = 0
    audio_downloads = 0
    image_downloads = 0
    recent_downloads = 0
    active_users = 0
    
    one_month_ago = datetime.now() - timedelta(days=30)
    one_week_ago = datetime.now() - timedelta(days=7)
    
    for uid, info in user_data.items():
        history = info.get('download_history', [])
        user_downloads = len(history)
        recent_user_downloads = sum(1 for h in history if datetime.fromisoformat(h['timestamp']) > one_week_ago)
        
        if user_downloads > 0 and datetime.fromisoformat(history[-1]['timestamp']) > one_month_ago:
            active_users += 1
        
        for h in history:
            if h['type'] == 'video':
                video_downloads += 1
            elif h['type'] == 'audio':
                audio_downloads += 1
            elif h['type'] == 'image':
                image_downloads += 1
            if datetime.fromisoformat(h['timestamp']) > one_week_ago:
                recent_downloads += 1
    
    total_feedback = len(feedback)
    total_channels = len(channels)
    
    return {
        'total_users': total_users,
        'total_downloads': total_downloads,
        'video_downloads': video_downloads,
        'audio_downloads': audio_downloads,
        'image_downloads': image_downloads,
        'recent_downloads': recent_downloads,
        'active_users': active_users,
        'total_feedback': total_feedback,
        'total_channels': total_channels
    }

# تابع اصلی
def main():
    # آپگرید yt-dlp در startup
    try:
        subprocess.run(['pip', 'install', '--upgrade', 'yt-dlp'], capture_output=True, check=True)
        logger.info("yt-dlp آپدیت شد.")
    except Exception as e:
        logger.error(f"خطا در آپدیت yt-dlp: {e}")
    
    application = Application.builder().token(TOKEN).build()

    start_handler = CommandHandler('start', start)
    application.add_handler(start_handler)

    notify_handler = CommandHandler('notify', notify_all_users)
    application.add_handler(notify_handler)

    set_lang_handler = MessageHandler(filters.Regex("^(فارسی|English)$"), set_language)
    application.add_handler(set_lang_handler)

    change_lang_handler = MessageHandler(filters.Regex("^(تغییر زبان|Change Language)$"), change_language_handler)
    application.add_handler(change_lang_handler)

    help_button_handler = MessageHandler(filters.Regex("^(راهنما|Help)$"), help_handler)
    application.add_handler(help_button_handler)

    download_prompt_handler_ = MessageHandler(filters.Regex("^(شروع دانلود|Start Download)$"), download_prompt_handler)
    application.add_handler(download_prompt_handler_)

    user_account_button_handler = MessageHandler(filters.Regex("^(حساب کاربری|User Account)$"), user_account_handler)
    application.add_handler(user_account_button_handler)
    
    feedback_button_handler = MessageHandler(filters.Regex("^(انتقادات و پیشنهادات|Feedback)$"), feedback_handler)
    application.add_handler(feedback_button_handler)
    
    contact_admin_button_handler = MessageHandler(filters.Regex("^(ارتباط با مدیر|Contact Admin)$"), contact_admin_handler)
    application.add_handler(contact_admin_button_handler)
    
    faq_button_handler = MessageHandler(filters.Regex("^(سوالات متداول|FAQ)$"), faq_handler)
    application.add_handler(faq_button_handler)

    message_handlers = MessageHandler(
        filters.TEXT & (~filters.COMMAND) & (
            ~filters.Regex("^(فارسی|English|راهنما|Help|تغییر زبان|Change Language|شروع دانلود|Start Download|حساب کاربری|User Account|انتقادات و پیشنهادات|Feedback|ارتباط با مدیر|Contact Admin|سوالات متداول|FAQ)$")
        ),
        handle_message_dispatcher
    )
    application.add_handler(message_handlers)
    
    type_choice_handler = CallbackQueryHandler(handle_type_choice, pattern="^type_")
    application.add_handler(type_choice_handler)
    
    watermark_choice_handler = CallbackQueryHandler(handle_watermark_choice, pattern="^watermark_")
    application.add_handler(watermark_choice_handler)
    
    admin_reply_button_handler = CallbackQueryHandler(handle_admin_reply_button, pattern="^reply_to_")
    application.add_handler(admin_reply_button_handler)
    
    faq_choice_handler = CallbackQueryHandler(handle_faq_choice, pattern="^faq_")
    application.add_handler(faq_choice_handler)

    admin_panel_cmd = CommandHandler('admin', admin_panel_handler)
    application.add_handler(admin_panel_cmd)

    membership_check_handler = CallbackQueryHandler(handle_membership_check, pattern="^check_membership$")
    application.add_handler(membership_check_handler)

    # به‌روزرسانی pattern برای شامل کردن back_to_manage_channels
    channel_mgmt_handler = CallbackQueryHandler(handle_channel_management, pattern="^(manage_channels|add_channel|list_channels|remove_channel_\d+|back_to_admin|bot_stats|monitoring|back_to_main|back_to_manage_channels)$")
    application.add_handler(channel_mgmt_handler)

    # هندلر جدید برای لغو عملیات
    cancel_handler = CallbackQueryHandler(handle_cancel, pattern="^(cancel_feedback|cancel_contact)$")
    application.add_handler(cancel_handler)
    
    instagram_login()
    application.run_polling(drop_pending_updates=True)

async def handle_message_dispatcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        is_member, not_joined_channels = await check_user_membership(user_id, context)
        if not is_member:
            lang = user_data.get(user_id, {}).get('lang', 'fa')
            await update.message.reply_text(
                MESSAGES[lang]['join_required'],
                reply_markup=get_join_channels_keyboard(not_joined_channels)
            )
            return
    
    if user_id == ADMIN_ID and context.user_data.get('awaiting_channel_info'):
        await handle_channel_info(update, context)
        return
    
    if user_id == ADMIN_ID and context.user_data.get('awaiting_admin_reply_to_user'):
        await handle_admin_reply_text(update, context)
    elif context.user_data.get('awaiting_feedback', False):
        await handle_feedback(update, context)
    elif context.user_data.get('awaiting_admin_message', False):
        await handle_admin_message(update, context)
    else:
        await handle_download_request(update, context)

if __name__ == '__main__':
    main()
