import logging
import asyncio
import requests
from telethon import TelegramClient, events
from solana.rpc.api import Client
from solana.transaction import Transaction
from solana.keypair import Keypair
from solana.publickey import PublicKey
from solana.rpc.types import TxOpts
import json
import os

# Đọc các biến môi trường
api_id = int(os.environ["API_ID"])
api_hash = os.environ["API_HASH"]
bot_token = os.environ["BOT_TOKEN"]

# Khởi tạo Telegram bot client
bot = TelegramClient('bot_session', api_id, api_hash).start(bot_token=bot_token)

# Lưu trạng thái người dùng
USER_STATE = {}

# Kết nối Solana RPC
solana = Client("https://api.mainnet-beta.solana.com")

# Lấy token mới nhất từ Pump.fun
def get_new_tokens():
    try:
        res = requests.get("https://client-api.pump.fun/all-tokens").json()
        sorted_tokens = sorted(res, key=lambda x: x['launchedAt'], reverse=True)
        return sorted_tokens[:1]  # lấy token mới nhất
    except:
        return []

# Mua token bằng cách gửi SOL
def buy_token(token_address, keypair: Keypair, amount_sol: float):
    try:
        dest = PublicKey(token_address)
        tx = Transaction()
        tx.add(
            solana.request_airdrop(dest, int(amount_sol * 1e9))["result"]
        )
        response = solana.send_transaction(tx, keypair, opts=TxOpts(skip_confirmation=False))
        return f"✅ Đã gửi {amount_sol} SOL đến token {token_address}\nTX: {response['result']}"
    except Exception as e:
        return f"❌ Lỗi khi gửi SOL đến token {token_address}:\n{e}"

# /start
@bot.on(events.NewMessage(pattern="/start"))
async def start(event):
    await event.respond("🤖 Xin chào! Gõ /nhap để nhập ví Solana và số lượng mua.")
    raise events.StopPropagation

# /nhap
@bot.on(events.NewMessage(pattern="/nhap"))
async def nhap(event):
    USER_STATE[event.chat_id] = {'step': 'await_key'}
    await event.respond("🛡️ Gửi PRIVATE KEY ví Solana của bạn (dạng mảng số):")
    raise events.StopPropagation

# Xử lý tin nhắn tiếp theo
@bot.on(events.NewMessage)
async def handle(event):
    user = USER_STATE.get(event.chat_id)
    if not user:
        return

    if user["step"] == "await_key":
        try:
            key_bytes = bytes(json.loads(event.raw_text.strip()))
            keypair = Keypair.from_secret_key(key_bytes)
            USER_STATE[event.chat_id]["keypair"] = keypair
            USER_STATE[event.chat_id]["step"] = "await_amount"
            await event.respond("💰 Nhập số lượng SOL muốn mua mỗi lần (VD: 0.1):")
        except Exception as e:
            await event.respond(f"❌ Lỗi private key: {e}")
    elif user["step"] == "await_amount":
        try:
            amount = float(event.raw_text.strip())
            if not 0.01 <= amount <= 1:
                await event.respond("❌ Vui lòng nhập từ 0.01 đến 1 SOL.")
                return
            USER_STATE[event.chat_id]["amount"] = amount
            USER_STATE[event.chat_id]["step"] = "done"
            await event.respond(f"✅ Cấu hình hoàn tất!\nBot sẽ tự động mua token mới trên pump.fun bằng {amount} SOL.")
            asyncio.create_task(sniper(event.chat_id))
        except:
            await event.respond("❌ Vui lòng nhập số hợp lệ.")

# Theo dõi và mua
async def sniper(chat_id):
    bought = set()
    while True:
        tokens = get_new_tokens()
        for token in tokens:
            token_addr = token["tokenAddress"]
            if token_addr in bought:
                continue
            bought.add(token_addr)
            keypair = USER_STATE[chat_id]["keypair"]
            amount = USER_STATE[chat_id]["amount"]
            result = buy_token(token_addr, keypair, amount)
            await bot.send_message(chat_id, result)
        await asyncio.sleep(5)

# Khởi chạy
def main():
    logging.basicConfig(level=logging.INFO)
    bot.run_until_disconnected()

if __name__ == "__main__":
    main()
