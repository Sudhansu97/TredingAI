"""
Telegram Polling Listener for RakshaQuant.
Handles private direct messages and group tags (@bot_username).
"""

import logging
import re
from html import escape

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

from scripts.agnt_workflow import create_interactive_graph
from src.config.settings import get_settings

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# Compile agent graph once
agent_app = create_interactive_graph(async_mode=True)


def format_telegram_html(text: str) -> str:
    """Keep only Telegram-supported HTML and remove Markdown code fences."""
    formatted = re.sub(r"```(?:html)?\s*|\s*```", "", text, flags=re.IGNORECASE)
    allowed_tags = r"b|strong|i|em|u|ins|s|strike|del|code|pre|tg-spoiler"
    formatted = re.sub(
        rf"</?(?!{allowed_tags}\b)[^>]+>",
        "",
        formatted,
        flags=re.IGNORECASE,
    )
    return formatted.strip()


async def edit_status_message(status_msg, text: str) -> None:
    """Edit a Telegram message as HTML, falling back safely on malformed markup."""
    formatted = format_telegram_html(text)
    try:
        await status_msg.edit_text(formatted, parse_mode=ParseMode.HTML)
    except BadRequest:
        await status_msg.edit_text(escape(re.sub(r"<[^>]+>", "", text)))


async def handle_incoming_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    chat_type = update.message.chat.type
    user_text = update.message.text

    print(f"Received message in {chat_type} chat: {user_text}")

    # 1. Filter when to process:
    # - PRIVATE chat: Process every text message.
    # - GROUP / SUPERGROUP chat: Process ONLY if the bot username is explicitly tagged.
    if chat_type in ["group", "supergroup"]:
        bot_username = context.bot.username
        if not bot_username:
            bot_username = (await context.bot.get_me()).username

        mention_pattern = rf"@{re.escape(bot_username)}\b"
        mention = re.search(mention_pattern, user_text, flags=re.IGNORECASE)
        if mention is None:
            return  # Ignore messages in group that don't tag the bot
        # Strip out the @mention from the prompt
        user_text = re.sub(mention_pattern, "", user_text, count=1, flags=re.IGNORECASE).strip()

    # Inform the user that analysis is in progress
    status_msg = await update.message.reply_text(
        "<i>Analyzing market indicators and news...</i>",
        parse_mode=ParseMode.HTML,
    )

    # 2. Invoke Agent Workflow
    initial_state = {
        "user_query": user_text,
        "target_symbol": "",
        "market_data": {},
        "regime": "",
        "regime_confidence": 0.0,
        "news_sentiment": {},
        "risk_assessment": {},
        "final_response": "",
    }

    try:
        output = await agent_app.ainvoke(initial_state)
        response_text = output.get("final_response", "Sorry, I couldn't process that query.")

        # Edit temporary status message with the completed response
        await edit_status_message(status_msg, response_text)
    except Exception as e:
        await edit_status_message(status_msg, f"<b>Error:</b> {escape(str(e))}")


def main():
    settings = get_settings()

    # Initialize Application with your Bot Token
    application = ApplicationBuilder().token(settings.telegram_bot_token).build()

    # Message Handler for standard text (excluding commands like /start)
    message_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, handle_incoming_message)
    application.add_handler(message_handler)

    logging.info("Telegram Bot is running and listening for queries...")
    application.run_polling()


if __name__ == "__main__":
    main()
