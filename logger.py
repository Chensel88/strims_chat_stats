import asyncio
import json
import sys
from typing import AsyncGenerator
from typing import List
from typing import TypedDict

import aiosqlite
import httpx
import websockets

EMOTE_MANIFEST = "https://chat.strims.gg/emote-manifest.json"
HOST = "wss://chat.strims.gg/ws"
DB_NAME = sys.argv[1] if len(sys.argv) > 1 else "bin/strims.db"
MSG = "MSG"
JOIN = "JOIN"
QUIT = "QUIT"
NAMES = "NAMES"
VIEWERSTATE = "VIEWERSTATE"


class User(TypedDict):
    nick: str
    features: List[str]


class ChatUsers(TypedDict):
    users: List[User]
    connectioncount: int


class Channel(TypedDict):
    channel: str
    service: str
    path: str


class ViewerState(TypedDict):
    nick: str
    online: bool
    channel: Channel


class EmoteInMsg(TypedDict):
    name: str
    modifiers: List[str]
    bounds: List[int]


class Nick(TypedDict):
    nick: str
    bounds: List[int]


class Entities(TypedDict):
    emotes: List[EmoteInMsg]
    nicks: List[Nick]


class Message(TypedDict):
    nick: str
    features: List[str]
    timestamp: int
    data: str
    entities: Entities


class Emote(TypedDict):
    name: str


async def get_emotes() -> List[Emote]:
    async with httpx.AsyncClient() as client:
        return (await client.get(EMOTE_MANIFEST)).json()["emotes"]


async def setup_db(path: str) -> aiosqlite.Connection:
    db = await aiosqlite.connect(path)
    create_users_table = """
CREATE TABLE IF NOT EXISTS users (
    nick TEXT PRIMARY KEY
);"""
    create_msgs_table = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    nick TEXT NOT NULL REFERENCES users (nick)
);"""
    create_entites_table = """
CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    data TEXT NOT NULL
);"""
    create_entity_in_msg_table = """
CREATE TABLE IF NOT EXISTS entity_in_msg (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    msgid INTEGER NOT NULL REFERENCES messages (id),
    entityid INTEGER NOT NULL REFERENCES entities (id)
);"""
    await db.execute(create_users_table)
    await db.execute(create_msgs_table)
    await db.execute(create_entites_table)
    await db.execute(create_entity_in_msg_table)
    await db.commit()
    return db


async def handle_msg(msg: str, db: aiosqlite.Connection):
    msg_type, json_msg = msg.split(None, 1)
    if msg_type == NAMES:
        names_msg: ChatUsers = json.loads(json_msg)
        print(f"We have {names_msg['connectioncount']} connections currently")
        await db.executemany(
            "INSERT OR IGNORE INTO users VALUES(?)",
            [(user["nick"],) for user in names_msg["users"]],
        )
        await db.commit()
    elif msg_type == JOIN:
        join_msg: User = json.loads(json_msg)
        print(f"{join_msg['nick']} has joined")
        await db.execute(
            "INSERT OR IGNORE INTO users VALUES(?)", (join_msg["nick"],),
        )
        await db.commit()
    elif msg_type == QUIT:
        ...
    elif msg_type == VIEWERSTATE:
        ...
    elif msg_type == MSG:
        chat_msg: Message = json.loads(json_msg)
        chat_msg_data = chat_msg["data"]
        print(f"{chat_msg['nick']}: {chat_msg_data}")
        mrow = await db.execute_insert(
            "INSERT INTO messages(data, timestamp, nick) VALUES(?,?,?)",
            (chat_msg_data, chat_msg["timestamp"], chat_msg["nick"]),
        )
        for emote in chat_msg.get("entities", {}).get("emotes", []):
            erow = await db.execute_insert(
                "INSERT INTO entities(type, data) VALUES(?, ?)",
                ("emote", emote["name"]),
            )
            await db.execute(
                "INSERT INTO entity_in_msg(msgid, entityid) VALUES(?,?)",
                (mrow[0], erow[0]),
            )

        await db.commit()
    else:
        print(msg_type, json_msg)


async def ws_handler() -> AsyncGenerator:
    async with websockets.connect(HOST, ping_interval=None) as ws:
        while True:
            try:
                msg = await ws.recv()
            except websockets.exceptions.ConnectionClosedOK as ex:  # CloudFlare WebSocket proxy restarting
                raise ex
            else:
                yield msg


async def run(db: aiosqlite.Connection):
    async for msg in ws_handler():
        await handle_msg(msg, db)


def main() -> int:
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    try:
        db = loop.run_until_complete(setup_db(DB_NAME))
        loop.run_until_complete(run(db))
    except Exception as ex:
        raise ex
    finally:
        loop.run_until_complete(db.close())
        loop.close()
    return 0


if __name__ == "__main__":
    exit(main())
