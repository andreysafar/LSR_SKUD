import logging
import re
import asyncio
import os
import threading
from typing import Dict, Any, Optional
from datetime import datetime

from config import get_config
from db.database import get_db
from parsec.api import ParsecAPI
from bot.handlers.auth import AuthHandler
from bot.handlers.passes import PassHandler
from bot.handlers.admin import AdminHandler
from training.collector import TrainingCollector
from training.manager import TrainingManager
from gate.controller import GateController

logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self):
        self.config = get_config()
        self.db = get_db(self.config.db_path)
        self.parsec = ParsecAPI(
            domain=self.config.parsec_domain,
            port=self.config.parsec_port,
            bot_username=self.config.parsec_bot_username,
            bot_password=self.config.parsec_bot_password,
            admin_username=self.config.parsec_admin_username,
            admin_password=self.config.parsec_admin_password,
        ) if self.config.parsec_domain else None

        self.auth_handler = AuthHandler(self.db, self.parsec)
        self.pass_handler = PassHandler(self.db, self.parsec)

        self.collector = TrainingCollector(self.config.training_data_dir)
        self.trainer = TrainingManager(
            self.config.training_data_dir,
            self.config.models_dir,
            self.config.min_training_samples,
        )

        self.admin_handler = AdminHandler(
            self.config.tech_chat_id,
            self.collector,
            self.trainer,
        )

        self.gate_controller = GateController(self.parsec)

        self.user_states: Dict[int, Dict[str, Any]] = {}
        self._bot = None
        self._bot_loop = None
        self._running = False

    async def start(self):
        if not self.config.telegram_bot_token:
            logger.warning("No Telegram bot token configured")
            return

        try:
            from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
            from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
            from telegram.ext import (
                ApplicationBuilder, CommandHandler, MessageHandler,
                CallbackQueryHandler, filters, ContextTypes
            )

            app = ApplicationBuilder().token(self.config.telegram_bot_token).build()

            app.add_handler(CommandHandler("start", self._cmd_start))
            app.add_handler(CommandHandler("help", self._cmd_help))
            app.add_handler(CommandHandler("passes", self._cmd_passes))
            app.add_handler(CommandHandler("set", self._cmd_set_group))
            app.add_handler(CommandHandler("cancel", self._cmd_cancel))
            app.add_handler(MessageHandler(filters.CONTACT, self._handle_contact))
            app.add_handler(CallbackQueryHandler(self._handle_callback))
            app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text))

            self._bot = app
            self._bot_loop = asyncio.get_event_loop()
            self._running = True
            logger.info("Telegram bot starting...")
            await app.initialize()
            await app.start()
            await app.updater.start_polling()
            logger.info("Telegram bot started")

        except ImportError:
            logger.error("python-telegram-bot not installed")
        except Exception as e:
            logger.error(f"Failed to start Telegram bot: {e}")

    async def stop(self):
        if self._bot and self._running:
            try:
                await self._bot.updater.stop()
                await self._bot.stop()
                await self._bot.shutdown()
            except Exception as e:
                logger.error(f"Error stopping bot: {e}")
            self._running = False

    async def send_review_to_admin(self, event_id: int, camera_id: str,
                                    result_data: Dict):
        if not self._bot or not self.config.tech_chat_id:
            return

        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup

            msg_data = self.admin_handler.create_review_message(
                event_id, camera_id, result_data
            )

            keyboard = []
            for row in msg_data["buttons"]:
                kb_row = []
                for btn in row:
                    kb_row.append(InlineKeyboardButton(
                        text=btn["text"], callback_data=btn["data"]
                    ))
                keyboard.append(kb_row)
            reply_markup = InlineKeyboardMarkup(keyboard)

            if msg_data.get("image_path") and os.path.exists(msg_data["image_path"]):
                with open(msg_data["image_path"], "rb") as photo:
                    sent = await self._bot.bot.send_photo(
                        chat_id=self.config.tech_chat_id,
                        photo=photo,
                        caption=msg_data["text"],
                        reply_markup=reply_markup,
                    )
            else:
                sent = await self._bot.bot.send_message(
                    chat_id=self.config.tech_chat_id,
                    text=msg_data["text"],
                    reply_markup=reply_markup,
                )

            if sent:
                self.db.update_recognition_event(
                    event_id, telegram_message_id=sent.message_id
                )

        except Exception as e:
            logger.error(f"Failed to send review to admin: {e}")

    async def _cmd_start(self, update, context):
        user_id = update.effective_user.id
        user = self.db.get_user(user_id)

        if user and user.get("parsec_person_id"):
            await update.message.reply_text(
                "Welcome back! You are authenticated.\n\n"
                "Send a license plate number (e.g. А123ВС77) to create a vehicle pass.\n"
                "Use /passes to view active passes.\n"
                "Use /help for all commands."
            )
            return

        from telegram import KeyboardButton, ReplyKeyboardMarkup
        button = KeyboardButton("📱 Share phone number", request_contact=True)
        reply_markup = ReplyKeyboardMarkup(
            [[button]], one_time_keyboard=True, resize_keyboard=True
        )
        await update.message.reply_text(
            "Welcome to the Gate Control Bot!\n\n"
            "Please share your phone number to authenticate with the Parsec system.",
            reply_markup=reply_markup,
        )

    async def _cmd_help(self, update, context):
        await update.message.reply_text(
            "🚗 Gate Control Bot Commands:\n\n"
            "/start - Start / authenticate\n"
            "/passes - View your active passes\n"
            "/set - Choose default access group\n"
            "/cancel - Cancel a pass\n"
            "/help - Show this help\n\n"
            "Send a license plate number to create a vehicle pass.\n"
            "Format: А123ВС77"
        )

    async def _cmd_passes(self, update, context):
        user_id = update.effective_user.id
        passes = self.pass_handler.get_user_passes(user_id)

        if not passes:
            await update.message.reply_text("You have no active passes.")
            return

        text_parts = ["📋 Your active passes:\n"]
        for p in passes:
            ptype = "🚗" if p["pass_type"] == "vehicle" else "🔑"
            plate_info = f" ({p['plate_number']})" if p.get("plate_number") else ""
            group_info = f" - {p.get('access_group_name', '')}" if p.get("access_group_name") else ""
            text_parts.append(
                f"{ptype} #{p['id']}{plate_info}{group_info}\n"
                f"   Valid: {p['valid_from']} → {p['valid_to']}"
            )

        await update.message.reply_text("\n".join(text_parts))

    async def _cmd_set_group(self, update, context):
        user_id = update.effective_user.id
        groups = self.auth_handler.get_user_access_groups(user_id)

        if not groups:
            await update.message.reply_text(
                "No access groups available. Make sure you are authenticated."
            )
            return

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = []
        for g in groups:
            keyboard.append([InlineKeyboardButton(
                g["name"], callback_data=f"grp:{g['id']}:{g['name']}"
            )])

        await update.message.reply_text(
            "Select your default access group:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def _cmd_cancel(self, update, context):
        user_id = update.effective_user.id
        passes = self.pass_handler.get_user_passes(user_id)

        if not passes:
            await update.message.reply_text("You have no active passes to cancel.")
            return

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = []
        for p in passes:
            label = f"#{p['id']}"
            if p.get("plate_number"):
                label += f" {p['plate_number']}"
            if p.get("access_group_name"):
                label += f" {p['access_group_name']}"
            keyboard.append([InlineKeyboardButton(
                f"❌ {label}", callback_data=f"cancel:{p['id']}"
            )])

        await update.message.reply_text(
            "Select a pass to cancel:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def _handle_contact(self, update, context):
        user_id = update.effective_user.id
        contact = update.message.contact
        phone = contact.phone_number

        result = self.auth_handler.authenticate_by_phone(user_id, phone)

        from telegram import ReplyKeyboardRemove
        if result["success"]:
            await update.message.reply_text(
                f"✅ {result['message']}\n\n"
                "Send a license plate number to create a vehicle pass.\n"
                "Use /set to choose your access group.",
                reply_markup=ReplyKeyboardRemove(),
            )
        else:
            await update.message.reply_text(
                f"❌ {result['message']}\n\nPlease try again or contact support.",
                reply_markup=ReplyKeyboardRemove(),
            )

    async def _handle_callback(self, update, context):
        query = update.callback_query
        data = query.data
        user_id = query.from_user.id

        if data.startswith("grp:"):
            parts = data.split(":", 2)
            group_id = parts[1]
            group_name = parts[2] if len(parts) > 2 else ""
            self.db.set_default_access_group(user_id, group_id)
            await query.answer(f"Default group set to: {group_name}")
            await query.edit_message_text(f"✅ Default access group: {group_name}")

        elif data.startswith("cancel:"):
            pass_id = int(data.split(":")[1])
            success = self.pass_handler.cancel_pass(pass_id, user_id)
            if success:
                await query.answer("Pass cancelled")
                await query.edit_message_text(f"✅ Pass #{pass_id} cancelled")
            else:
                await query.answer("Failed to cancel pass")

        elif data.startswith("duration:"):
            parts = data.split(":")
            duration = parts[1]
            state = self.user_states.get(user_id, {})
            plate = state.get("plate")
            if plate:
                result = self.pass_handler.create_vehicle_pass(user_id, plate, duration)
                await query.answer(result["message"])
                await query.edit_message_text(
                    f"✅ {result['message']}" if result["success"]
                    else f"❌ {result['message']}"
                )
                self.user_states.pop(user_id, None)
            else:
                await query.answer("Please send a plate number first")

        elif data.startswith("rv:"):
            chat_id = update.effective_chat.id
            if chat_id == self.config.tech_chat_id:
                result = self.admin_handler.process_callback(data)
                await query.answer(result["response_text"][:200])

                if result.get("need_text_input"):
                    self.user_states[user_id] = {
                        "waiting_ocr_correction": True,
                        "event_id": result["event_id"],
                    }
                    await query.message.reply_text(result["response_text"])
                elif result["response_text"]:
                    try:
                        await query.edit_message_reply_markup(reply_markup=None)
                    except Exception:
                        pass

    async def _handle_text(self, update, context):
        user_id = update.effective_user.id
        text = update.message.text.strip()

        state = self.user_states.get(user_id, {})
        if state.get("waiting_ocr_correction"):
            event_id = state["event_id"]
            result = self.admin_handler.process_ocr_correction(event_id, text)
            await update.message.reply_text(
                f"✅ {result['message']}" if result["success"]
                else f"❌ {result['message']}"
            )
            self.user_states.pop(user_id, None)
            return

        user = self.db.get_user(user_id)
        if not user:
            await update.message.reply_text(
                "Please authenticate first. Use /start"
            )
            return

        if self.pass_handler.is_plate_like(text):
            from recognition.ocr_engine import normalize_plate
            plate = normalize_plate(text)
            self.user_states[user_id] = {"plate": plate}

            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            keyboard = [
                [InlineKeyboardButton("Until end of day", callback_data="duration:day_end")],
                [InlineKeyboardButton("3 hours", callback_data="duration:3hours")],
                [InlineKeyboardButton("24 hours", callback_data="duration:24hours")],
                [InlineKeyboardButton("1 week", callback_data="duration:week")],
            ]

            await update.message.reply_text(
                f"🚗 Creating pass for: {plate}\n\nSelect duration:",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        else:
            await update.message.reply_text(
                "I didn't recognize a license plate number.\n"
                "Please send it in format: А123ВС77\n\n"
                "Use /help for available commands."
            )

    def on_recognition_result(self, result):
        if not result or not result.vehicle_detected:
            return

        event_id = self.db.save_recognition_event(
            camera_id=result.camera_id,
            **result.to_dict()
        )

        if result.normalized_plate:
            gate_result = self.gate_controller.check_plate_and_open(
                result.camera_id, result.normalized_plate, event_id
            )

            if gate_result["gate_opened"]:
                logger.info(f"Gate opened for {result.normalized_plate}")

        if self._bot and self.config.tech_chat_id and self._bot_loop:
            result_data = result.to_dict()
            result_data["frame_path"] = result.frame_path
            result_data["plate_image_path"] = result.plate_image_path

            try:
                asyncio.run_coroutine_threadsafe(
                    self.send_review_to_admin(event_id, result.camera_id, result_data),
                    self._bot_loop,
                )
            except Exception as e:
                logger.error(f"Failed to schedule admin review: {e}")
