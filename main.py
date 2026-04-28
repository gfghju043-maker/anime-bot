import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# --- SOZLAMALAR ---
TOKEN = "8636087303:AAEsZvZ6JO0lD8mCwtbuIQBnTBDAejZgCnE"
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
        self.cursor.execute("INSERT INTO playlist_items (playlist_id, movie_id, order_idx) VALUES (?, ?, ?)", (pl_id, m_id, idx))
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
    text = "📋 **Hozirgi kanallar:**\n\n"
    if channels:
        for c in channels: text += f"🆔 {c[0]} | {c[1]}\n"
    else: text += "Kanallar yo'q."
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Qo'shish", callback_data="add_ch")],
        [InlineKeyboardButton(text="🗑 O'chirish", callback_data="del_ch_list")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "add_ch")
async def add_ch_call(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_channel)
    await call.message.answer("Kanal username'ini yuboring (@kanal):")
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
        await call.answer("O'chirishga kanal yo'q!", show_alert=True)
        return
    btns = [[InlineKeyboardButton(text=f"❌ {c[1]}", callback_data=f"removech_{c[0]}")] for c in channels]
    await call.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("removech_"))
async def remove_ch_final(call: CallbackQuery):
    ch_id = int(call.data.split("_")[1])
    db.delete_channel(ch_id)
    await call.answer("✅ Kanal o'chirildi!", show_alert=True)
    await call.message.delete()

# 2. PLAYLISTDAN KINO O'CHIRISH
@dp.message(F.text == "🗑 Playlistdan kino o'chirish", F.from_user.id == ADMIN_ID)
async def pl_del_start(message: Message, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_pl_del_pid)
    await message.answer("🆔 Playlist ID-sini yuboring (Masalan: 1):")

@dp.message(AdminStates.waiting_for_pl_del_pid, F.text.isdigit())
async def pl_del_pid(message: Message, state: FSMContext):
    await state.update_data(pid=message.text)
    items = db.cursor.execute("SELECT m.id, m.caption FROM movies m JOIN playlist_items pi ON m.id = pi.movie_id WHERE pi.playlist_id=?", (message.text,)).fetchall()
    if items:
        text = "📋 Kinolar:\n" + "\n".join([f"🆔 {i[0]} - {i[1]}" for i in items])
        await message.answer(text + "\n\nO'chirmoqchi bo'lgan kino ID-sini yuboring:")
        await state.set_state(AdminStates.waiting_for_pl_del_mid)
    else:
        await message.answer("Playlist bo'sh."); await state.clear()

@dp.message(AdminStates.waiting_for_pl_del_mid, F.text.isdigit())
async def pl_del_done(message: Message, state: FSMContext):
    data = await state.get_data()
    db.remove_from_playlist(int(data['pid']), int(message.text))
    await message.answer("✅ O'chirildi."); await state.clear()

# 3. KINO VA PLAYLIST QO'SHISH
@dp.message(F.text == "🎬 Kino qo'shish", F.from_user.id == ADMIN_ID)
async def m_add(message: Message, state: FSMContext):
    await state.set_state(AdminStates.adding_movie_video)
    await message.answer("📽 Video yoki fayl yuboring:")

@dp.message(AdminStates.adding_movie_video, F.video | F.document)
async def m_v(message: Message, state: FSMContext):
    fid = message.video.file_id if message.video else message.document.file_id
    await state.update_data(vid=fid); await state.set_state(AdminStates.adding_movie_name)
    await message.answer("📝 Kino nomini yozing:")

@dp.message(AdminStates.adding_movie_name)
async def m_n(message: Message, state: FSMContext):
    data = await state.get_data()
    mid = db.add_movie(data['vid'], message.text)
    await message.answer(f"✅ Saqlandi! ID: `{mid}`", parse_mode="Markdown"); await state.clear()

@dp.message(F.text == "🗂 Playlist yaratish", F.from_user.id == ADMIN_ID)
async def pl_create(message: Message, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_pl_name)
    await message.answer("📝 Playlist nomi:")

@dp.message(AdminStates.waiting_for_pl_name)
async def pl_save(message: Message, state: FSMContext):
    res = db.create_playlist(message.text)
    await message.answer(f"✅ Kod: `PL{res}`" if res else "❌ Xato", parse_mode="Markdown"); await state.clear()

@dp.message(F.text == "➕ Playlistga qo'shish", F.from_user.id == ADMIN_ID)
async def pl_add_mid(message: Message, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_pl_add_mid)
    await message.answer("🆔 Kino ID raqamini yuboring:")

@dp.message(AdminStates.waiting_for_pl_add_mid, F.text.isdigit())
async def pl_add_choose(message: Message, state: FSMContext):
    pls = db.cursor.execute("SELECT id, name FROM playlists").fetchall()
    if not pls: await message.answer("Playlist yo'q!"); await state.clear(); return
    btns = [[InlineKeyboardButton(text=p[1], callback_data=f"plsave_{p[0]}_{message.text}")] for p in pls]
    await message.answer("Playlistni tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns)); await state.clear()

# --- QIDIRUV VA STATISTIKA ---

@dp.message(F.text.isdigit())
async def get_m(message: Message):
    if not await check_sub(message.from_user.id):
        await message.answer("❌ Kanallarga a'zo bo'ling!"); return
    res = db.cursor.execute("SELECT file_id, caption FROM movies WHERE id=?", (message.text,)).fetchone()
    if res: await message.answer_video(video=res[0], caption=res[1])
    else: await message.answer("❌ Topilmadi.")

@dp.message(F.text.lower().startswith("pl"))
async def get_pl(message: Message):
    if not await check_sub(message.from_user.id):
        await message.answer("❌ Obuna bo'ling!"); return
    try:
        pl_id = int(message.text.upper().replace("PL", ""))
        items = db.cursor.execute("SELECT m.file_id, m.caption FROM movies m JOIN playlist_items pi ON m.id = pi.movie_id WHERE pi.playlist_id=? ORDER BY pi.order_idx ASC", (pl_id,)).fetchall()
        if items:
            for m in items: await message.answer_video(video=m[0], caption=m[1]); await asyncio.sleep(0.5)
        else: await message.answer("📭 Bo'sh.")
    except: await message.answer("❌ Xato kod.")

@dp.callback_query(F.data.startswith("plsave_"))
async def pl_save_f(call: CallbackQuery):
    _, pl_id, m_id = call.data.split("_")
    db.add_to_playlist(int(pl_id), int(m_id))
    await call.answer("✅ Qo'shildi!", show_alert=True); await call.message.delete()

@dp.message(F.text == "📋 Playlistlar ro'yxati", F.from_user.id == ADMIN_ID)
async def pl_list_all(message: Message):
    pls = db.cursor.execute("SELECT id, name FROM playlists").fetchall()
    text = "🗂 Playlistlar:\n\n" + "\n".join([f"PL{p[0]} - {p[1]}" for p in pls]) if pls else "Ro'yxat bo'sh."
    await message.answer(text)

@dp.message(F.text == "📊 Statistika", F.from_user.id == ADMIN_ID)
async def show_stats(message: Message):
    u = db.cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    m = db.cursor.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
    await message.answer(f"👤 Foydalanuvchilar: {u}\n🎬 Kinolar: {m}")

@dp.message(F.text == "📢 Reklama", F.from_user.id == ADMIN_ID)
async def ad_s(message: Message, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_ad); await message.answer("📣 Xabar yuboring:")

@dp.message(AdminStates.waiting_for_ad)
async def ad_d(message: Message, state: FSMContext):
    users = db.cursor.execute("SELECT user_id FROM users").fetchall()
    for u in users:
        try: await message.copy_to(u[0]); await asyncio.sleep(0.05)
        except: pass
    await message.answer("✅ Tarqatildi."); await state.clear()

@dp.message(F.text == "🗑 Kino o'chirish", F.from_user.id == ADMIN_ID)
async def del_movie_main(message: Message, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_del_id); await message.answer("🆔 Kino ID yuboring:")

@dp.message(AdminStates.waiting_for_del_id, F.text.isdigit())
async def del_movie_done(message: Message, state: FSMContext):
    db.delete_movie(int(message.text)); await message.answer("✅ Bazadan o'chirildi."); await state.clear()

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
