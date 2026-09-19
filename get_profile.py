


import os
import logging
from telegram import Update, ChatMember
from telegram.ext import Updater, CommandHandler, CallbackContext
from dotenv import load_dotenv
import csv

# Configuration
load_dotenv()
TOKEN = os.environ["LEGACY_ACCOUNTER_BOT_TOKEN"]
CHAT_ID = -1002332110966  # Your group chat ID (keep the negative sign)
ADMIN_ID = [93027469]  # Your user ID(s) to restrict access

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def get_member_ids(update: Update, context: CallbackContext):
    """Synchronous function to get all member IDs"""
    if update.effective_user.id not in ADMIN_ID:
        update.message.reply_text("❌ Command restricted to admin")
        return

    try:
        update.message.reply_text("🔄 Collecting member IDs...")
        
        # Get all chat members (synchronous version)
        members = context.bot.get_chat_members(chat_id=CHAT_ID)
        
        # Prepare data
        member_data = []
        for member in members:
            user = member.user
            member_data.append([
                user.id,
                user.first_name,
                user.last_name or '',
                f"@{user.username}" if user.username else 'N/A',
                str(member.status)
            ])
        
        # Create CSV
        filename = "group_members.csv"
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['ID', 'First Name', 'Last Name', 'Username', 'Status'])
            writer.writerows(member_data)
        
        # Send file
        with open(filename, 'rb') as f:
            context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=f,
                caption=f"✅ Found {len(member_data)} members"
            )
            
    except Exception as e:
        logger.error(f"Error: {e}")
        update.message.reply_text(f"❌ Error: {e}")

def main():
    """Start the bot."""
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # Command handlers
    dp.add_handler(CommandHandler("get_ids", get_member_ids))

    updater.start_polling()
    logger.info("Bot is running...")
    updater.idle()

if __name__ == '__main__':
    main()