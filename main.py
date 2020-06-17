import asyncio
import json
from enum import Enum
from typing import Dict
from typing import List
from typing import TypedDict

import aiohttp
import websockets

HOST = "wss://chat.strims.gg/ws"


class Dimensions(TypedDict):
    height: int
    width: int


class Size(Enum):
    THE_1_X = "1x"
    THE_2_X = "2x"
    THE_4_X = "4x"


class Version(TypedDict):
    path: str
    animated: bool
    dimensions: Dimensions
    size: Size


class Emote(TypedDict):
    name: str
    versions: List[Version]


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


async def get_emotes() -> Dict[str, List[Emote]]:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://chat.strims.gg/emote-manifest.json",
        ) as response:
            return await response.json()


async def handler(emotes: List[Emote]) -> None:
    emote_count: Dict[str, int] = {}
    for emote in emotes:
        emote_count.update({emote["name"]: 0})

    async with websockets.connect(HOST, ping_interval=None) as ws:
        while True:
            msg = await ws.recv()
            msg_type, json_msg = msg.split(None, 1)

            if msg_type == "NAMES":
                names_msg: ChatUsers = json.loads(json_msg)
                print(f"We have {names_msg['connectioncount']} connections currently")
            elif msg_type == "QUIT":
                quit_msg: User = json.loads(json_msg)
                print(f"{quit_msg['nick']} has quit")
            elif msg_type == "JOIN":
                join_msg: User = json.loads(json_msg)
                print(f"{join_msg['nick']} has joined")
            elif msg_type == "VIEWERSTATE":
                vs_msg: ViewerState = json.loads(json_msg)
                if vs_msg["online"] and "channel" in vs_msg:
                    print(
                        f"{vs_msg['nick']} is watching {vs_msg['channel']['channel']}",
                    )
            elif msg_type == "MSG":
                chat_msg: Message = json.loads(json_msg)
                chat_msg_data = chat_msg["data"]
                for entity in chat_msg.get("entities", {}).get("emotes", []):
                    emote_count[entity["name"]] += 1

                print(f"{chat_msg['nick']}: {chat_msg_data}")
            else:
                print(msg_type, json_msg)


def main() -> int:
    loop = asyncio.get_event_loop()
    emotes = loop.run_until_complete(get_emotes())
    print(emotes)
    loop.run_until_complete(handler(emotes["emotes"]))
    loop.run_forever()
    loop.close()
    return 0


if __name__ == "__main__":
    exit(main())
