import os
import json
import logging
import random
import string
import io
import time
from datetime import datetime

from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

import qrcode
from PIL import Image

import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ================= SECURE CONFIG =================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0"))

UPI_ID = os.environ.get("UPI_ID", "")
UPI_NAME = os.environ.get("UPI_NAME", "")

SUPPORT_LINK = os.environ.get("SUPPORT_LINK", "")
SHEET_NAME = os.environ.get("SHEET_NAME", "ATTRAH_ORDERS")
logging.basicConfig(level=logging.INFO)

ORDERS = {}
DISPATCH_INPUT = {}

PRICES = {
    "Dubai Mafia": {"3ml": 399, "6ml": 649, "8ml": 849, "12ml": 1199},
    "Pine Desire": {"3ml": 329, "6ml": 499, "8ml": 699, "12ml": 999},
    "Edible Musk": {"3ml": 319, "6ml": 499, "8ml": 699, "12ml": 999},
    "Skin Obsessed": {"3ml": 299, "6ml": 399, "8ml": 599, "12ml": 899},
    "Coco Crave": {"3ml": 299, "6ml": 399, "8ml": 599, "12ml": 899}
}

# ================= GOOGLE SHEETS =================

def init_sheet():
    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]

        creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
        if not creds_json:
            logging.error("GOOGLE_CREDENTIALS_JSON not found")
            return None
            
        creds_dict = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)

        client = gspread.authorize(creds)
        return client.open(SHEET_NAME).sheet1
    except Exception as e:
        logging.error(f"Failed to init sheet: {e}")
        return None
    

SHEET = init_sheet()

def get_column_map():
    if not SHEET: return {}
    try:
        headers = SHEET.row_values(1)
        return {h.strip(): i + 1 for i, h in enumerate(headers)}
    except:
        return {}

def sheet_append(order):
    if not SHEET: return
    col = get_column_map()
    row = [""] * (max(col.values()) if col else 15)

    def set_col(name, value):
        if name in col:
            row[col[name] - 1] = value

    set_col("Order ID", order.get("order_id", ""))
    set_col("Telegram User ID", order.get("user_id", ""))  
    set_col("Customer Name", order.get("name", ""))
    set_col("Mobile Number", order.get("mobile", ""))
    set_col("Product", order.get("product", ""))
    set_col("Size", order.get("size", ""))
    set_col("Pcs", order.get("pcs", ""))
    set_col("Amount", order.get("amount", ""))
    set_col("Full Address", order.get("address", ""))
    set_col("Payment Status", order.get("status", ""))
    set_col("Payment Time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    set_col("Tracking ID", order.get("tracking_id", ""))
    set_col("Tracking Link", order.get("tracking_url", ""))
    set_col("Dispatch Status", order.get("Dispatch_Status", ""))
    set_col("Courier", order.get("courier", ""))

    SHEET.append_row(row)

def sheet_update(order_id, status, tracking_id="", tracking_url=""):
    if not SHEET: return
    col = get_column_map()
    records = SHEET.get_all_records()

    for i, r in enumerate(records, start=2):
        if r.get("Order ID") == order_id:
            if "Payment Status" in col:
                SHEET.update_cell(i, col["Payment Status"], status)
            if "Payment Time" in col:
                SHEET.update_cell(
                    i,	
                    col["Payment Time"],
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
            if tracking_id and "Tracking ID" in col:
                SHEET.update_cell(i, col["Tracking ID"], tracking_id)
            if tracking_url and "Tracking Link" in col:
                SHEET.update_cell(i, col["Tracking Link"], tracking_url)
            if "Dispatch Status" in col:
                SHEET.update_cell(i, col["Dispatch Status"], status)
            break

def get_orders_from_sheet_by_user(user_id):
    if not SHEET: return []
    try:
        records = SHEET.get_all_records()
        orders = []
        for row in records:
            if str(row.get("Telegram User ID")) == str(user_id):
                orders.append({
                    "order_id": row.get("Order ID"),
                    "product": row.get("Product"),
                    "size": row.get("Size"),
                    "pcs": row.get("Pcs"),
                    "amount": row.get("Amount"),
                    "status": row.get("Payment Status"),
                    "courier": row.get("Courier"),
                    "tracking_id": row.get("Tracking ID"),
                    "tracking_url": row.get("Tracking Link")
                })
        return orders
    except:
        return []

def get_order_by_id(order_id):
    if not SHEET: return None
    try:
        records = SHEET.get_all_records()
        for row in records:
            if row.get("Order ID") == order_id:
                return {
                    "order_id": row.get("Order ID"),
                    "user_id": row.get("Telegram User ID"),
                    "name": row.get("Customer Name"),
                    "product": row.get("Product"),
                    "size": row.get("Size"),
                    "pcs": row.get("Pcs"),
                    "amount": row.get("Amount"),
                    "address": row.get("Full Address"),
                    "status": row.get("Payment Status"),
                    "courier": row.get("Courier"),
                    "tracking_id": row.get("Tracking ID"),
                    "tracking_url": row.get("Tracking Link"),
                }
        return None
    except:
        return None

# ================= HELPERS =================
SAFE_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"
SAFE_DIGITS = "23456789"

def generate_order_id():
    date_part = datetime.now().strftime("%y%m%d")
    unique_part = "".join(random.choices(SAFE_LETTERS + SAFE_DIGITS, k=6))
    return f"ATR {date_part} {unique_part}"

def main_menu():
    return ReplyKeyboardMarkup(
        [
            ["🛒 Place Order", "📦 Active Order"],
            ["🧾 Order Summary", "📍 Delivery Status"],
            ["💰 Payment Status", "📞 Contact Support"]
        ],
        resize_keyboard=True
    )

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to ATTRAH\n\n"
        "We specialize in premium attars crafted with care and long-lasting elegance.\n\n"
        "You can place orders, complete secure payments, and track delivery updates directly from this bot.\n\n"
        "Please use the menu below to continue.",
        reply_markup=main_menu()
    )

# ================= ORDER FLOW =================
async def place_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["step"] = "name"
    await update.message.reply_text("👤 Please enter your Full Name:")

async def active_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    all_orders = get_orders_from_sheet_by_user(user_id)
    user_orders = [o for o in all_orders if o.get("status") != "Dispatched"]

    if not user_orders:
        await update.message.reply_text(
            "📦 No Active Orders Found\n\n"
            "You don’t have any active orders at the moment.\n"
            "Tap 🛒 Place Order to create a new one.",
            reply_markup=main_menu()
        )
        return

    priority = {"Payment Pending": 1, "Payment Rejected": 2, "Payment Verified": 3}
    order = sorted(user_orders, key=lambda x: priority.get(x.get("status", ""), 99))[0]

    status_message = {
        "Payment Pending": "⏳ Awaiting payment.\nPlease complete the payment and upload the screenshot.",
        "Payment Rejected": "❌ Payment was rejected.\nPlease re-upload a clear payment screenshot.",
        "Payment Verified": "✅ Payment verified.\nYour order is being prepared for dispatch."
    }.get(order["status"], "ℹ️ Order is being processed.")

    await update.message.reply_text(
        f"📦 Your Active Order\n\n"
        f"🧾 Order ID: {order['order_id']}\n"
        f"🧴 Product: {order['product']}\n"
        f"📦 Size: {order['size']}\n"
        f"🔢 Pcs: {order['pcs']}\n"
        f"💰 Amount: ₹{order['amount']}\n\n"
        f"📌 Status: {order['status']}\n\n"
        f"{status_message}",
        reply_markup=main_menu()
    )

async def order_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_orders = get_orders_from_sheet_by_user(user_id)

    if not user_orders:
        await update.message.reply_text(
            "🧾 Order Summary\n\n"
            "You haven’t placed any orders yet.\n"
            "Tap 🛒 Place Order to get started.",
            reply_markup=main_menu()
        )
        return

    user_orders = list(reversed(user_orders))
    message_lines = ["🧾 Your Order Summary\n"]
    for idx, order in enumerate(user_orders, start=1):
        message_lines.append(
            f"{idx}️⃣ {order['order_id']}\n"
            f"🧴 {order['product']} | {order['size']} | ₹{order['amount']}\n"
            f"📌 Status: {order['status']}\n"
        )
    await update.message.reply_text("\n".join(message_lines), reply_markup=main_menu())

async def payment_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_orders = get_orders_from_sheet_by_user(user_id)

    if not user_orders:
        await update.message.reply_text(
            "💰 Payment Status\n\n"
            "You haven’t placed any orders yet.\n"
            "Tap 🛒 Place Order to begin.",
            reply_markup=main_menu()
        )
        return

    order = list(user_orders)[-1]
    status = order.get("status", "Unknown")
    status_message = {
        "Payment Pending": "⏳ Payment Pending\n\nWe haven’t received a verified payment yet.\nPlease complete the payment using the QR and upload the screenshot.",
        "Payment Rejected": "❌ Payment Rejected\n\nWe were unable to verify your payment.\nPlease re-upload a clear payment screenshot or retry the payment.",
        "Payment Verified": "✅ Payment Verified\n\nYour payment has been successfully verified.\nYour order is now being prepared for dispatch.",
        "Dispatched": "🚚 Payment Verified & Order Dispatched\n\nYour payment was verified and the order has already been shipped.\nYou can check delivery details under 📍 Delivery Status."
    }.get(status, "ℹ️ Payment information is being processed.")

    await update.message.reply_text(
        f"💰 Payment Status\n\n"
        f"🧾 Order ID: {order['order_id']}\n"
        f"💵 Amount: ₹{order['amount']}\n"
        f"📌 Current Status: {status}\n\n"
        f"{status_message}",
        reply_markup=main_menu()
    )

async def delivery_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    all_orders = get_orders_from_sheet_by_user(user_id)
    dispatched_orders = [o for o in all_orders if o.get("status") == "Dispatched"]

    if not dispatched_orders:
        await update.message.reply_text(
            "📍 Delivery Status\n\n"
            "You don't have any dispatched orders yet.\n"
            "Once your order is shipped, the tracking details will appear here.",
            reply_markup=main_menu()
        )
        return

    dispatched_orders = list(reversed(dispatched_orders))
    message_lines = ["📍 Delivery Status\n"]
    for idx, order in enumerate(dispatched_orders, start=1):
        message_lines.append(
            f"{idx}️⃣ Order ID: {order['order_id']}\n"
            f"📦 Courier: {order.get('courier', 'Not provided')}\n"
            f"🔢 Tracking ID: {order.get('tracking_id', 'Not provided')}\n"
            f"🌐 Track here: {order.get('tracking_url', 'Not provided')}\n"
        )
    await update.message.reply_text("\n".join(message_lines), reply_markup=main_menu())

async def contact_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📞 Contact Support\n\nIf you have any questions or need help with your order, please reach out to us: {SUPPORT_LINK}",
        reply_markup=main_menu()
    )

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get("step")
    text = update.message.text

    if step == "name":
        context.user_data["name"] = text
        context.user_data["step"] = "mobile"
        await update.message.reply_text("📱 Please enter your Mobile Number:")
    elif step == "mobile":
        context.user_data["mobile"] = text
        context.user_data["step"] = "address"
        await update.message.reply_text("🏠 Please enter your Full Delivery Address:")
    elif step == "address":
        context.user_data["address"] = text
        context.user_data["step"] = "product"
        keyboard = [[p] for p in PRICES.keys()]
        await update.message.reply_text("🧴 Select a Product:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    elif step == "product":
        if text in PRICES:
            context.user_data["product"] = text
            context.user_data["step"] = "size"
            keyboard = [[s] for s in PRICES[text].keys()]
            await update.message.reply_text("📦 Select Size:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        else:
            await update.message.reply_text("Invalid product. Please select from the menu.")
    elif step == "size":
        product = context.user_data.get("product")
        if text in PRICES.get(product, {}):
            context.user_data["size"] = text
            context.user_data["step"] = "pcs"
            await update.message.reply_text("🔢 How many pieces (Pcs)?")
        else:
            await update.message.reply_text("Invalid size. Please select from the menu.")
    elif step == "pcs":
        try:
            pcs = int(text)
            context.user_data["pcs"] = pcs
            product = context.user_data.get("product")
            size = context.user_data.get("size")
            amount = PRICES[product][size] * pcs
            context.user_data["amount"] = amount
            
            order_id = generate_order_id()
            context.user_data["order_id"] = order_id
            
            order = {
                "order_id": order_id,
                "user_id": update.effective_user.id,
                "name": context.user_data["name"],
                "mobile": context.user_data["mobile"],
                "address": context.user_data["address"],
                "product": product,
                "size": size,
                "pcs": pcs,
                "amount": amount,
                "status": "Payment Pending"
            }
            
            sheet_append(order)
            
            # QR Code Generation
            upi_url = f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={amount}&cu=INR&tn=Order {order_id}"
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(upi_url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            
            bio = io.BytesIO()
            bio.name = 'qr.png'
            img.save(bio, 'PNG')
            bio.seek(0)
            
            await update.message.reply_photo(
                photo=bio,
                caption=(
                    f"✅ Order Placed Successfully!\n\n"
                    f"🧾 Order ID: {order_id}\n"
                    f"💰 Total Amount: ₹{amount}\n\n"
                    f"Please pay using the QR above or UPI ID: `{UPI_ID}`\n\n"
                    "After payment, please upload the screenshot here."
                ),
                reply_markup=main_menu()
            )
            context.user_data["step"] = "payment_proof"
        except ValueError:
            await update.message.reply_text("Please enter a valid number for pieces.")

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("step") == "payment_proof" or True: # Allow anytime for safety
        order_id = context.user_data.get("order_id")
        if not order_id:
            user_id = update.effective_user.id
            orders = get_orders_from_sheet_by_user(user_id)
            if orders:
                order_id = orders[-1]["order_id"]
        
        if order_id:
            photo_file = await update.message.photo[-1].get_file()
            # In a real app, we'd save this file. Here we just notify admin.
            await context.bot.send_photo(
                chat_id=ADMIN_CHAT_ID,
                photo=photo_file.file_id,
                caption=f"🚨 New Payment Screenshot!\nOrder ID: {order_id}\nUser: {update.effective_user.full_name}"
            )
            await update.message.reply_text("✅ Payment screenshot received! We will verify it soon.")
            context.user_data["step"] = None

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN not set")
    else:
        app = ApplicationBuilder().token(BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.Text("🛒 Place Order"), place_order))
        app.add_handler(MessageHandler(filters.Text("📦 Active Order"), active_order))
        app.add_handler(MessageHandler(filters.Text("🧾 Order Summary"), order_summary))
        app.add_handler(MessageHandler(filters.Text("📍 Delivery Status"), delivery_status))
        app.add_handler(MessageHandler(filters.Text("💰 Payment Status"), payment_status))
        app.add_handler(MessageHandler(filters.Text("📞 Contact Support"), contact_support))
        app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
        print("Bot is running...")
        app.run_polling()
