import logging
import asyncio
import requests
from telethon import TelegramClient, events
from solana.rpc.api import Client
from solana.transaction import Transaction
from solana.keypair import Keypair
from solana.publickey import PublicKey
from solana.rpc.types import TxOpts
from base64 import b64decode
import json
import os

# Đọc các biến môi trường
api_id = int(os.environ["API_ID"])
api_hash = os.environ["API_HASH"]
bot_token = os.environ["BOT_TOKEN"]

# Khởi tạo Telegram bot client
bot = TelegramClient('bot_session', api_id, api_hash).start(bot_token=bot_token)

# Tạo nơi lưu thông tin người dùng
USER_STATE = {}

# Kết nối RPC Solana
solana = Client("https://api.mainnet-beta.solana.com")

# Lấy danh sách token mới trên Pump.fun
def get_new_tokens():
    try:
        res = requests.get("https://client-api.pump.fun/all-tokens").json()
        sorted_tokens = sorted(res, key=lambda x: x['launchedAt'], reverse=True)
        return sorted_tokens[:1]  # chỉ lấy 1 token mới nhất
    except Exception as e:
        return []

# Gửi SOL để mua token
def buy_token(token_address, keypair: Keypair, amount_sol: float):
    try:
        # Gửi native SOL đến địa chỉ token -> Pump sẽ tự xử lý giao dịch
        tx = Transaction()
        tx.add(
            solana.request_airdrop(
                PublicKey(token_address), int(amount_sol * 10**9)
            )["result"]
        )
        response = solana.send_transaction(tx, keypair, opts=TxOpts(skip_confirmation=False))
        return f"Đã mua token: {token_address}\nTX: {response['result']}"
    except Exception as e:
        return f"❌ Lỗi khi mua token: {e}"

# Hàm xử lý lệnh /start
@bot.on(events.NewMessage(pattern="/start"))
async def start(event):
    await event.respond("🤖 Xin chào! Gõ /nhap để bắt đầu cấu hình ví và số lượng mua.")
    raise events.StopPropagation

# Nhập private key và số lượng SOL
@bot.on(events.NewMessage(pattern="/nhap"))
async def handle_nhap(event):
    USER_STATE[event.chat_id] = {'step': 'awaiting_key'}
    await event.respond("🛡️ Vui lòng gửi PRIVATE KEY ví Solana của bạn:")
    raise events.StopPropagation

@bot.on(events.NewMessage)
async def handle_message(event):
    user = USER_STATE.get(event.chat_id)

    if not user:
        return

    if user.get("step") == "awaiting_key":
        try:
            key = event.raw_text.strip()
            if key.startswith('['):  # dạng array
                key_bytes = bytes(json.loads(key))
            else:  # dạng base58 (tạm không dùng)
                await event.respond("❌ Chỉ hỗ trợ private key dạng mảng JSON.")
                return
            kp = Keypair.from_secret_key(key_bytes)
            USER_STATE[event.chat_id]["keypair"] = kp
            USER_STATE[event.chat_id]["step"] = "awaiting_amount"
            await event.respond("✅ Nhập số SOL muốn dùng cho mỗi lần mua (VD: 0.1):")
        except Exception as e:
            await event.respond(f"❌ Private key không hợp lệ: {e}")

    elif user.get("step") == "awaiting_amount":
        try:
            amount = float(event.raw_text.strip())
            if 0.01 <= amount <= 1:
                USER_STATE[event.chat_id]["amount"] = amount
                USER_STATE[event.chat_id]["step"] = "ready"
                await event.respond("✅ Cấu hình hoàn tất! Bot sẽ bắt đầu theo dõi token mới...")
                asyncio.create_task(sniper(event.chat_id))  # chạy ngầm
            else:
                await event.respond("❌ Nhập số từ 0.01 đến 1 SOL.")
        except:
            await event.respond("❌ Số không hợp lệ.")

# Theo dõi và mua token
async def sniper(chat_id):
    bought = set()
    while True:
        tokens = get_new_tokens()
        for token in tokens:
            addr = token["tokenAddress"]
            if addr not in bought:
                bought.add(addr)
                keypair = USER_STATE[chat_id]["keypair"]
                amount = USER_STATE[chat_id]["amount"]
                result = buy_token(addr, keypair, amount)
                await bot.send_message(chat_id, result)
        await asyncio.sleep(5)

# Khởi chạy bot
def main():
    logging.basicConfig(level=logging.INFO)
    bot.run_until_disconnected()

if __name__ == "__main__":
    main()
