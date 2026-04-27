import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# --- SOZLAMALAR ---
TOKEN = "8658700234:AAH9UAodf490eDdZsS_ix3SZKHtzzXNWD6E"
ADMIN_ID = 8684039353 

# --- MA'LUMOTLAR BAZASI ---
class Database:
    def __init__(self, db_name="movies.db"):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        self.cursor.execute("CREATE TABLE IF NOT EXISTS movies (id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT, caption TEXT)")
        self.cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
        self.cursor.execute("CREATE TABLE IF NOT EXISTS playlists (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE)")
        self.cursor.execute("CREATE TABLE IF NOT EXISTS playlist_items (playlist_id INTEGER, movie_id INTEGER, order_idx INTEGER)")
        self.cursor.execute("CREATE TABLE IF NOT EXISTS channels (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT)")
        self.conn.commit()

    def add_user(self, user_id):
        try:
            self.cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
            self.conn.commit()
        except: pass

    def add_movie(self, file_id, caption):
        self.cursor.execute("INSERT INTO movies (file_id, caption) VALUES (?, ?)", (file_id, caption))
        self.conn.commit()
        return self.cursor.lastrowid

    def delete_movie(self, movie_id):
        self.cursor.execute("DELETE FROM movies WHERE id=?", (movie_id,))
        self.cursor.execute("DELETE FROM playlist_items WHERE movie_id=?", (movie_id,))
        self.conn.commit()

    def create_playlist(self, name):
        try:
            self.cursor.execute("INSERT INTO playlists (name) VALUES (?)", (name,))
            self.conn.commit()
            return self.cursor.lastrowid
        except: return None

    def add_to_playlist(self, pl_id, m_id):
        self.cursor.execute("SELECT MAX(order_idx) FROM playlist_items WHERE playlist_id = ?", (pl_id,))
        res = self.cursor.fetchone()[0]
        idx = (res + 1) if res is not None else 1
        self.cursor.execute("INSERT INTO playlist_items VALUES (?, ?, ?)", (pl_id, m_id, idx))
        self.conn.commit()

    def remove_from_playlist(self, pl_id, m_id):
        self.cursor.execute("DELETE FROM playlist_items WHERE playlist_id=? AND movie_id=?", (pl_id, m_id))
        self.conn.commit()

    def delete_channel(self, ch_id):
        self.cursor.execute("DELETE FROM channels WHERE id=?", (ch_id,))
        self.conn.commit()

db = Database()
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- HOLATLAR (FSM) ---
class AdminStates(StatesGroup):
    waiting_for_pl_name = State()
    adding_movie_video = State()
    adding_movie_name = State()
    waiting_for_ad = State()
    waiting_for_del_id = State()
    waiting_for_pl_add_mid = State()
    waiting_for_channel = State()
    waiting_for_pl_del_pid = State()
    waiting_for_pl_del_mid = State()

# --- TUGMALAR ---
def admin_main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🎬 Kino qo'shish"), KeyboardButton(text="🗑 Kino o'chirish")],
        [KeyboardButton(text="🗂 Playlist yaratish"), KeyboardButton(text="➕ Playlistga qo'shish")],
        [KeyboardButton(text="🗑 Playlistdan kino o'chirish"), KeyboardButton(text="📋 Playlistlar ro'yxati")],
        [KeyboardButton(text="📢 Reklama"), KeyboardButton(text="🔐 Kanallar sozlamasi")],
        [KeyboardButton(text="📊 Statistika")]
    ], resize_keyboard=True)

# --- MAJBURIY OBUNA TEKSHIRUVI ---
async def check_sub(user_id):
    channels = db.cursor.execute("SELECT username FROM channels").fetchall()
    if not channels: return True
    for ch in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch[0], user_id=user_id)
            if member.status in ["left", "kicked"]: return False
        except: continue
    return True

# --- ADMIN HANDLERLAR ---

@dp.message(Command("start"))
async def cmd_start(message: Message):
    db.add_user(message.from_user.id)
    if message.from_user.id == ADMIN_ID:
        await message.answer("🛠 Admin panelga xush kelibsiz!", reply_markup=admin_main_kb())
    else:
        await message.answer("🎬 Salom! Kino kodini yoki Playlist ID-sini yuboring (Masalan: PL1).")

# 1. KANALLAR SOZLAMASI
@dp.message(F.text == "🔐 Kanallar sozlamasi", F.from_user.id == ADMIN_ID)
async def ch_settings(message: Message):
    channels = db.cursor.execute("SELECT id, username FROM channels").fetchall()
    text = "📋 **Hozirgi kanallar ro'yxati:**\n\n"
    if channels:
        for c in channels:
            text += f"🆔 {c[0]} | {c[1]}\n"
    else:
        text += "Hali kanallar qo'shilmagan."
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="add_ch")],
        [InlineKeyboardButton(text="🗑 Kanalni o'chirish", callback_data="del_ch_list")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "add_ch")
async def add_ch_call(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_channel)
    await call.message.answer("Kanal username'ini yuboring (Masalan: @kanal_nomi):")
    await call.answer()

@dp.message(AdminStates.waiting_for_channel)
async def save_ch(message: Message, state: FSMContext):
    db.cursor.execute("INSERT INTO channels (username) VALUES (?)", (message.text,))
    db.conn.commit()
    await message.answer(f"✅ {message.text} qo'shildi!", reply_markup=admin_main_kb())
    await state.clear()

@dp.callback_query(F.data == "del_ch_list")
async def del_ch_list(call: CallbackQuery):
    channels = db.cursor.execute("SELECT id, username FROM channels").fetchall()
    if not channels:
        await call.answer("O'chirish uchun kanallar yo'q!", show_alert=True)
        return
    btns = [[InlineKeyboardButton(text=f"❌ {c[1]}", callback_data=f"removech_{c[0]}")] for c in channels]
    await call.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("removech_"))
async def remove_ch_final(call: CallbackQuery):
    ch_id = int(call.data.split("_")[1])
    db.delete_channel(ch_id)
    await call.answer("✅ Kanal olib tashlandi!", show_alert=True)
    await call.message.delete()

# 2. PLAYLISTLAR
@dp.message(F.text == "🗂 Playlist yaratish", F.from_user.id == ADMIN_ID)
async def pl_create(message: Message, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_pl_name)
    await message.answer("📝 Playlist nomini yozing:")

@dp.message(AdminStates.waiting_for_pl_name)
async def pl_save(message: Message, state: FSMContext):
    res = db.create_playlist(message.text)
    if res: await message.answer(f"✅ Yaraldi: `PL{res}`", parse_mode="Markdown")
    else: await message.answer("❌ Xatolik.")
    await state.clear()

@dp.message(F.text == "➕ Playlistga qo'shish", F.from_user.id == ADMIN_ID)
async def pl_add_mid(message: Message, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_pl_add_mid)
    await message.answer("🆔 Kino ID raqamini yuboring:")

@dp.message(AdminStates.waiting_for_pl_add_mid, F.text.isdigit())
async def pl_add_choose(message: Message, state: FSMContext):
    pls = db.cursor.execute("SELECT id, name FROM playlists").fetchall()
    if not pls:
        await message.answer("Playlistlar yo'q!"); await state.clear(); return
    btns = [[InlineKeyboardButton(text=p[1], callback_data=f"plsave_{p[0]}_{message.text}")] for p in pls]
    await message.answer("Playlistni tanlang:", reply_
