import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, \
    CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# --- SOZLAMALAR ---
TOKEN = "8636087303:AAEsZvZ6JO0lD8mCwtbuIQBnTBDAejZgCnE"
ADMIN_ID = 8684039353


# Ma'lumotlar bazasi boshqaruvi
class Database:
    def __init__(self, db_name="movies.db"):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        # Kinolar jadvali
        self.cursor.execute(
            "CREATE TABLE IF NOT EXISTS movies (id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT, caption TEXT)")
        # Playlistlar nomi
        self.cursor.execute(
            "CREATE TABLE IF NOT EXISTS playlists (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE)")
        # Playlist ichidagi kinolar (Tartibi bilan)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS playlist_items (
                playlist_id INTEGER, 
                movie_id INTEGER, 
                order_idx INTEGER,
                FOREIGN KEY(playlist_id) REFERENCES playlists(id),
                FOREIGN KEY(movie_id) REFERENCES movies(id)
            )""")
        self.conn.commit()

    def add_movie(self, file_id, caption):
        self.cursor.execute("INSERT INTO movies (file_id, caption) VALUES (?, ?)", (file_id, caption))
        self.conn.commit()
        return self.cursor.lastrowid

    def create_playlist(self, name):
        try:
            self.cursor.execute("INSERT INTO playlists (name) VALUES (?)", (name,))
            self.conn.commit()
            return self.cursor.lastrowid
        except:
            return None

    def get_playlists(self):
        self.cursor.execute("SELECT id, name FROM playlists")
        return self.cursor.fetchall()

    def add_to_playlist(self, pl_id, m_id):
        self.cursor.execute("SELECT MAX(order_idx) FROM playlist_items WHERE playlist_id = ?", (pl_id,))
        res = self.cursor.fetchone()[0]
        new_idx = (res + 1) if res is not None else 1
        self.cursor.execute("INSERT INTO playlist_items VALUES (?, ?, ?)", (pl_id, m_id, new_idx))
        self.conn.commit()

    def get_playlist_content(self, pl_id):
        self.cursor.execute("""
            SELECT m.file_id, m.caption FROM movies m 
            JOIN playlist_items pi ON m.id = pi.movie_id 
            WHERE pi.playlist_id = ? ORDER BY pi.order_idx ASC
        """, (pl_id,))
        return self.cursor.fetchall()

    def delete_playlist(self, pl_id):
        self.cursor.execute("DELETE FROM playlist_items WHERE playlist_id = ?", (pl_id,))
        self.cursor.execute("DELETE FROM playlists WHERE id = ?", (pl_id,))
        self.conn.commit()


db = Database()
bot = Bot(token=TOKEN)
dp = Dispatcher()


# --- HOLATLAR ---
class AdminStates(StatesGroup):
    waiting_for_pl_name = State()
    adding_movie_video = State()
    adding_movie_name = State()


# --- TUGMALAR ---
def admin_main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🎬 Kino qo'shish"), KeyboardButton(text="🗂 Playlist yaratish")],
        [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="🗑 Playlistni o'chirish")]
    ], resize_keyboard=True)


def movie_action_kb(movie_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Playlistga qo'shish", callback_data=f"pladd_{movie_id}")]
    ])


# --- ADMIN HANDLERLAR ---

@dp.message(Command("start"))
async def cmd_start(message: Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("🛠 Admin panelga xush kelibsiz!", reply_markup=admin_main_kb())
    else:
        await message.answer("🎬 Kino kodini yuboring yoki playlist ID-sini yozing (masalan: PL1).")


# --- PLAYLIST YARATISH ---
@dp.message(F.text == "🗂 Playlist yaratish", F.from_user.id == ADMIN_ID)
async def pl_create_start(message: Message, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_pl_name)
    await message.answer("📝 Playlist uchun nom yozing (masalan: Seriallar yoki Marvel):")


@dp.message(AdminStates.waiting_for_pl_name)
async def pl_create_save(message: Message, state: FSMContext):
    res = db.create_playlist(message.text)
    if res:
        await message.answer(f"✅ Playlist yaratildi!\n🆔 Chaqirish kodi: `PL{res}`", parse_mode="Markdown")
    else:
        await message.answer("❌ Bunday nomli playlist bor.")
    await state.clear()


# --- KINO QO'SHISH VA PLAYLIST TUGMASI ---
@dp.message(F.text == "🎬 Kino qo'shish", F.from_user.id == ADMIN_ID)
async def movie_add_start(message: Message, state: FSMContext):
    await state.set_state(AdminStates.adding_movie_video)
    await message.answer("📽 Kino faylini yuboring:")


@dp.message(AdminStates.adding_movie_video, F.video | F.document)
async def movie_add_video(message: Message, state: FSMContext):
    fid = message.video.file_id if message.video else message.document.file_id
    await state.update_data(vid=fid)
    await state.set_state(AdminStates.adding_movie_name)
    await message.answer("📝 Kino nomini yozing:")


@dp.message(AdminStates.adding_movie_name)
async def movie_add_done(message: Message, state: FSMContext):
    data = await state.get_data()
    m_id = db.add_movie(data['vid'], message.text)
    await message.answer(f"✅ Kino saqlandi! ID: `{m_id}`",
                         reply_markup=movie_action_kb(m_id), parse_mode="Markdown")
    await state.clear()


# --- PLAYLISTGA QO'SHISH (CALLBACK) ---
@dp.callback_query(F.data.startswith("pladd_"))
async def pl_choose(call: CallbackQuery):
    m_id = call.data.split("_")[1]
    pls = db.get_playlists()
    if not pls:
        await call.answer("Avval playlist yarating!", show_alert=True)
        return

    btns = [[InlineKeyboardButton(text=p[1], callback_data=f"plsave_{p[0]}_{m_id}")] for p in pls]
    await call.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))


@dp.callback_query(F.data.startswith("plsave_"))
async def pl_save_final(call: CallbackQuery):
    _, pl_id, m_id = call.data.split("_")
    db.add_to_playlist(int(pl_id), int(m_id))
    await call.answer("✅ Muvaffaqiyatli qo'shildi!", show_alert=True)
    await call.message.edit_reply_markup(reply_markup=None)


# --- PLAYLISTNI CHAQIRISH (KETMA-KET) ---
@dp.message(F.text.startswith("PL"))
async def get_pl(message: Message):
    try:
        pl_id = int(message.text.replace("PL", ""))
        movies = db.get_playlist_content(pl_id)
        if movies:
            await message.answer(f"📦 Playlist yuklanmoqda ({len(movies)} ta kino)...")
            for m in movies:
                await message.answer_video(video=m[0], caption=m[1])
                await asyncio.sleep(0.5)  # Ketma-ketlik va xavfsizlik uchun
        else:
            await message.answer("📭 Bu playlist bo'sh.")
    except:
        await message.answer("❌ Noto'g'ri playlist kodi.")


# --- ODDIY QIDIRUV ---
@dp.message(F.text.isdigit())
async def get_m(message: Message):
    res = db.cursor.execute("SELECT file_id, caption FROM movies WHERE id=?", (message.text,)).fetchone()
    if res:
        kb = movie_action_kb(message.text) if message.from_user.id == ADMIN_ID else None
        await message.answer_video(video=res[0], caption=res[1], reply_markup=kb)
    else:
        await message.answer("Topilmadi.")


async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())