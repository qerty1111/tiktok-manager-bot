import aiosqlite
import json
from typing import List, Optional, Dict, Any
from config import DB_PATH

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                username TEXT DEFAULT '',
                cookies_json TEXT NOT NULL,
                proxy TEXT DEFAULT '',
                avatar_url TEXT DEFAULT '',
                followers_count INTEGER DEFAULT 0,
                views_count INTEGER DEFAULT 0,
                likes_count INTEGER DEFAULT 0,
                video_count INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                last_checked TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                tiktok_video_id TEXT DEFAULT '',
                title TEXT DEFAULT '',
                views_count INTEGER DEFAULT 0,
                likes_count INTEGER DEFAULT 0,
                comments_count INTEGER DEFAULT 0,
                video_url TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS upload_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                description TEXT DEFAULT '',
                hashtags TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                error_message TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE
            )
        """)
        await db.commit()

async def get_video_by_id(video_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM videos WHERE id = ?", (video_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_all_accounts() -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM accounts ORDER BY id ASC") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_account_by_id(account_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

get_account = get_account_by_id

async def add_account(name: str, cookies_json: str, proxy: str = "", username: str = "") -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        cursor = await db.execute(
            """
            INSERT INTO accounts (name, cookies_json, proxy, username)
            VALUES (?, ?, ?, ?)
            """,
            (name, cookies_json, proxy, username)
        )
        await db.commit()
        return cursor.lastrowid

async def update_account_stats(
    account_id: int,
    username: str = "",
    avatar_url: str = "",
    followers: int = 0,
    views: int = 0,
    likes: int = 0,
    video_count: int = 0,
    is_active: int = 1
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(
            """
            UPDATE accounts
            SET username = COALESCE(NULLIF(?, ''), username),
                avatar_url = COALESCE(NULLIF(?, ''), avatar_url),
                followers_count = ?,
                views_count = ?,
                likes_count = ?,
                video_count = ?,
                is_active = ?,
                last_checked = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (username, avatar_url, followers, views, likes, video_count, is_active, account_id)
        )
        await db.commit()

async def update_account_cookies(account_id: int, cookies_json: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(
            "UPDATE accounts SET cookies_json = ?, is_active = 1 WHERE id = ?",
            (cookies_json, account_id)
        )
        await db.commit()

async def update_account_proxy(account_id: int, proxy: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(
            "UPDATE accounts SET proxy = ? WHERE id = ?",
            (proxy, account_id)
        )
        await db.commit()

async def delete_account(account_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        await db.commit()

async def get_account_videos(account_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM videos WHERE account_id = ? ORDER BY id DESC LIMIT ?",
            (account_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def save_account_video(
    account_id: int,
    tiktok_video_id: str,
    title: str,
    views: int,
    likes: int,
    comments: int,
    video_url: str
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(
            """
            INSERT INTO videos (account_id, tiktok_video_id, title, views_count, likes_count, comments_count, video_url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (account_id, tiktok_video_id, title, views, likes, comments, video_url)
        )
        await db.commit()
