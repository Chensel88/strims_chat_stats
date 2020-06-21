import asyncio
import json
from typing import AsyncGenerator
from typing import List
from typing import TypedDict

import aiosqlite
import httpx
import websockets

HOST = "wss://chat.strims.gg/ws"
EMOTE_MANIFEST = "https://chat.strims.gg/emote-manifest.json"
DB_NAME = "strims.db"
MSG = "MSG"
JOIN = "JOIN"
QUIT = "QUIT"
VIEWERSTATE = "VIEWERSTATE"
NAMES = "NAMES"


class Emote(TypedDict):
    name: str


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


async def setup_db(path: str) -> aiosqlite.Connection:
    db = await aiosqlite.connect(path)
    create_users_statement = """
CREATE TABLE IF NOT EXISTS users (
    nick TEXT PRIMARY KEY
);"""
    create_msgs_statement = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    nick TEXT NOT NULL,
    FOREIGN KEY (nick)
        REFERENCES users (nick)
);"""
    await db.execute(create_users_statement)
    await db.execute(create_msgs_statement)
    await db.commit()
    return db


async def get_emotes() -> List[Emote]:
    async with httpx.AsyncClient() as client:
        return (await client.get(EMOTE_MANIFEST)).json()["emotes"]


# link count by type
# link count by site
# user msg count
# emote count overall and by user
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
    elif msg_type == QUIT:
        quit_msg: User = json.loads(json_msg)
        print(f"{quit_msg['nick']} has quit")
    elif msg_type == JOIN:
        join_msg: User = json.loads(json_msg)
        print(f"{join_msg['nick']} has joined")
        await db.execute(
            "INSERT OR IGNORE INTO users VALUES(?)", (join_msg["nick"],),
        )
        await db.commit()
    elif msg_type == VIEWERSTATE:
        ...
    elif msg_type == MSG:
        chat_msg: Message = json.loads(json_msg)
        chat_msg_data = chat_msg["data"]
        print(f"{chat_msg['nick']}: {chat_msg_data}")
        await db.execute(
            "INSERT INTO messages(data, timestamp, nick) VALUES(?,?,?)",
            (chat_msg_data, chat_msg["timestamp"], chat_msg["nick"]),
        )
        await db.commit()
    else:
        print(msg_type, json_msg)


async def ws_handler(emotes: List[Emote]) -> AsyncGenerator:
    async with websockets.connect(HOST, ping_interval=None) as ws:
        while True:
            try:
                msg = await ws.recv()
            except websockets.exceptions.ConnectionClosedOK as ex:  # CloudFlare WebSocket proxy restarting
                raise ex
            else:
                yield msg


async def run(db: aiosqlite.Connection, emotes: List[Emote]):
    async for msg in ws_handler(emotes):
        await handle_msg(msg, db)


def main() -> int:
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    try:
        db = loop.run_until_complete(setup_db(DB_NAME))
        emotes = loop.run_until_complete(get_emotes())
        loop.run_until_complete(run(db, emotes))
    except Exception as ex:
        raise ex
    finally:
        loop.run_until_complete(db.close())
        loop.close()
    return 0


if __name__ == "__main__":
    exit(main())
