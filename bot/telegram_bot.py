import logging
import re
import asyncio
import os
import subprocess
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

# Admin group for logs, coordination and feedback (same as tech_chat_id in config)
FEEDBACK_BUTTON_CALLBACK = "feedback:start"


def _feedback_keyboard():
    """Inline keyboard with single button: send next user message to admin group."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📩 Сообщить о проблеме / написать в админ-группу", callback_data=FEEDBACK_BUTTON_CALLBACK)]
    ])


def _get_git_info() -> Dict[str, str]:
    """Get current git commit hash, subject and branch for startup notification."""
    result = {}
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for key, cmd in [
        ("commit", ["git", "rev-parse", "HEAD"]),
        ("subject", ["git", "log", "-1", "--pretty=%s"]),
        ("branch", ["git", "branch", "--show-current"]),
    ]:
        try:
            out = subprocess.run(
                cmd, cwd=root, capture_output=True, text=True, timeout=2
            )
            if out.returncode == 0 and out.stdout:
                result[key] = out.stdout.strip()
            else:
                result[key] = ""
        except Exception:
            result[key] = ""
    return result


class TelegramBot:
    def __init__(self):
        self.config = get_config()
        self.db = get_db(self.config.db_path)
        self.parsec = ParsecAPI(
            host=self.config.parsec_domain,
            port=self.config.parsec_port,
            organization=self.config.parsec_organization,
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
        logger.info("Bot start() called, token=%s, proxy=%s",
                    "set" if self.config.telegram_bot_token else "NOT SET",
                    self.config.telegram_proxy_url or "none")
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
            from telegram.request import HTTPXRequest

            builder = ApplicationBuilder().token(self.config.telegram_bot_token)
            if self.config.telegram_proxy_url:
                logger.info("Using Telegram proxy: %s", self.config.telegram_proxy_url)
                builder = builder.request(HTTPXRequest(proxy=self.config.telegram_proxy_url))
            else:
                logger.warning("TELEGRAM_PROXY_URL not set - API calls may fail behind corporate proxy")
            app = builder.build()

            app.add_handler(CommandHandler("start", self._cmd_start))
            app.add_handler(CommandHandler("help", self._cmd_help))
            app.add_handler(CommandHandler("passes", self._cmd_passes))
            app.add_handler(CommandHandler("set", self._cmd_set_group))
            app.add_handler(CommandHandler("cancel", self._cmd_cancel))
            app.add_handler(MessageHandler(filters.CONTACT, self._handle_contact))
            app.add_handler(CallbackQueryHandler(self._handle_callback))
            app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text))
            app.add_error_handler(self._on_error)

            self._bot = app
            self._bot_loop = asyncio.get_event_loop()
            self._running = True
            logger.info("Telegram bot starting...")
            await app.initialize()
            await app.start()
            await app.updater.start_polling()
            logger.info("Telegram bot started")
            await self._send_startup_notification()

        except ImportError as e:
            logger.error("python-telegram-bot not installed: %s", e, exc_info=True)
        except Exception as e:
            logger.error("Failed to start Telegram bot: %s", e, exc_info=True)

    async def _on_error(self, update: object, context: Any) -> None:
        """Log errors and notify admin group so there is feedback when something goes wrong."""
        import traceback
        logger.exception("Telegram bot error: %s", context.error)
        if not self._bot or not self.config.tech_chat_id:
            return
        try:
            err_msg = str(context.error) or "Unknown error"
            short = err_msg[:400] + "…" if len(err_msg) > 400 else err_msg
            text = (
                "⚠️ Ошибка в боте\n\n"
                f"{short}\n\n"
                "Подробности в логах сервера. При повторении — напишите в эту группу."
            )
            await self._bot.bot.send_message(
                chat_id=self.config.tech_chat_id,
                text=text,
            )
        except Exception as e:
            logger.warning("Could not send error to admin group: %s", e)

    async def _send_startup_notification(self) -> None:
        """Send reboot notification to admin group (tech_chat_id)."""
        if not self._bot or not self.config.tech_chat_id:
            return
        try:
            git = _get_git_info()
            commit = git.get("commit", "")[:7] if git.get("commit") else "—"
            subject = git.get("subject", "") or "—"
            branch = git.get("branch", "") or "—"
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            text = (
                "🔄 Бот был перезапущен\n\n"
                f"🔖 Последний коммит: {commit}\n"
                f"📝 Сообщение: {subject}\n"
                f"🌿 Ветка: {branch}\n\n"
                f"⏱️ Время запуска: {now}"
            )
            await self._bot.bot.send_message(
                chat_id=self.config.tech_chat_id,
                text=text,
            )
        except Exception as e:
            logger.warning("Could not send startup notification: %s", e)

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
        chat = update.effective_chat
        user = self.db.get_user(user_id)

        # In groups we cannot request phone — ask to open bot in private
        if chat.type != "private":
            await update.message.reply_text(
                "Авторизация возможна только в личном чате с ботом.\n"
                "Напишите боту в личные сообщения (Direct) и нажмите /start.\n\n"
                "При проблемах нажмите кнопку ниже — ваше сообщение будет переслано в админ-группу.",
                reply_markup=_feedback_keyboard(),
            )
            return

        if user and user.get("parsec_person_id"):
            await update.message.reply_text(
                "С возвращением! Вы уже авторизованы.\n\n"
                "Отправьте номер авто (например А123ВС77), чтобы создать пропуск.\n"
                "Команды: /passes — ваши пропуска, /set — группа доступа, /help — справка.\n\n"
                "При проблемах нажмите кнопку ниже.",
                reply_markup=_feedback_keyboard(),
            )
            return

        from telegram import KeyboardButton, ReplyKeyboardMarkup
        button = KeyboardButton("📱 Поделиться номером телефона", request_contact=True)
        reply_markup = ReplyKeyboardMarkup(
            [[button]], one_time_keyboard=True, resize_keyboard=True
        )
        await update.message.reply_text(
            "Добро пожаловать в бот контроля доступа!\n\n"
            "Поделитесь номером телефона для авторизации в системе Parsec.",
            reply_markup=reply_markup,
        )

    async def _cmd_help(self, update, context):
        await update.message.reply_text(
            "🚗 Бот контроля доступа — команды:\n\n"
            "/start — запуск и авторизация\n"
            "/passes — ваши активные пропуска\n"
            "/set — выбор группы доступа по умолчанию\n"
            "/cancel — отмена пропуска\n"
            "/help — эта справка\n\n"
            "Отправьте номер авто (формат А123ВС77), чтобы создать пропуск.\n\n"
            "При проблемах нажмите кнопку ниже.",
            reply_markup=_feedback_keyboard(),
        )

    async def _cmd_passes(self, update, context):
        user_id = update.effective_user.id
        passes = self.pass_handler.get_user_passes(user_id)

        if not passes:
            await update.message.reply_text("У вас нет активных пропусков.")
            return

        text_parts = ["📋 Ваши активные пропуска:\n"]
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
                "Нет доступных групп доступа. Сначала авторизуйтесь через /start."
            )
            return

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = []
        for g in groups:
            keyboard.append([InlineKeyboardButton(
                g["name"], callback_data=f"grp:{g['id']}:{g['name']}"
            )])

        await update.message.reply_text(
            "Выберите группу доступа по умолчанию:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def _cmd_cancel(self, update, context):
        user_id = update.effective_user.id
        passes = self.pass_handler.get_user_passes(user_id)

        if not passes:
            await update.message.reply_text("Нет активных пропусков для отмены.")
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
            "Выберите пропуск для отмены:",
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
                "Отправьте номер авто для создания пропуска. Команда /set — выбор группы доступа.",
                reply_markup=ReplyKeyboardRemove(),
            )
        else:
            await update.message.reply_text(
                f"❌ {result['message']}\n\nПовторите попытку или нажмите кнопку ниже, чтобы написать в админ-группу.",
                reply_markup=ReplyKeyboardRemove(),
            )
            await update.message.reply_text(
                "При проблемах ваше сообщение перешлём в админ-группу.",
                reply_markup=_feedback_keyboard(),
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
            await query.answer(f"Группа по умолчанию: {group_name}")
            await query.edit_message_text(f"✅ Группа доступа: {group_name}")

        elif data.startswith("cancel:"):
            pass_id = int(data.split(":")[1])
            success = self.pass_handler.cancel_pass(pass_id, user_id)
            if success:
                await query.answer("Пропуск отменён")
                await query.edit_message_text(f"✅ Пропуск #{pass_id} отменён")
            else:
                await query.answer("Не удалось отменить пропуск")

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
                await query.answer("Сначала отправьте номер авто")

        elif data == FEEDBACK_BUTTON_CALLBACK:
            self.user_states[user_id] = {"waiting_feedback": True}
            await query.answer()
            await query.message.reply_text(
                "Опишите проблему или вопрос. Ваше следующее сообщение будет переслано в админ-группу."
            )
            return

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
        user_obj = update.effective_user

        state = self.user_states.get(user_id, {})
        if state.get("waiting_feedback"):
            self.user_states.pop(user_id, None)
            if self.config.tech_chat_id and self._bot:
                try:
                    name = user_obj.full_name or "?"
                    username = f"@{user_obj.username}" if user_obj.username else "—"
                    admin_text = (
                        f"📩 Сообщение от пользователя:\n"
                        f"{name} (ID: {user_id}, {username})\n\n{text}"
                    )
                    await self._bot.bot.send_message(
                        chat_id=self.config.tech_chat_id,
                        text=admin_text,
                    )
                    await update.message.reply_text("✅ Сообщение доставлено в админ-группу.")
                except Exception as e:
                    logger.warning("Failed to forward feedback to admin group: %s", e)
                    await update.message.reply_text("Не удалось отправить в админ-группу. Попробуйте позже.")
            else:
                await update.message.reply_text("Админ-группа не настроена. Обратитесь к администратору.")
            return

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
                "Сначала авторизуйтесь: /start"
            )
            return

        if self.pass_handler.is_plate_like(text):
            from recognition.ocr_engine import normalize_plate
            plate = normalize_plate(text)
            self.user_states[user_id] = {"plate": plate}

            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            keyboard = [
                [InlineKeyboardButton("До конца дня", callback_data="duration:day_end")],
                [InlineKeyboardButton("3 часа", callback_data="duration:3hours")],
                [InlineKeyboardButton("24 часа", callback_data="duration:24hours")],
                [InlineKeyboardButton("1 неделя", callback_data="duration:week")],
            ]

            await update.message.reply_text(
                f"🚗 Создание пропуска: {plate}\n\nВыберите срок:",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        else:
            await update.message.reply_text(
                "Не похоже на номер авто. Отправьте в формате А123ВС77.\n\n"
                "Команда /help — справка по командам. При проблемах — кнопка ниже.",
                reply_markup=_feedback_keyboard(),
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
