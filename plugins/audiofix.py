# /audiofix — standalone feature.
#
# Independent of plugins/batch.py and its existing save-restricted-content
# workflow. Does not import from or modify batch.py in any way.
#
# Purpose: scan a channel (bot must be admin there) for media files that
# are named like video (.mp4 etc.) but actually contain only an audio
# stream, and DM the corrected file (proper audio, correct extension)
# to the user via their configured delivery bot (/setbot).

import os
import asyncio
import time

from pyrogram import Client, filters
from pyrogram.types import Message

from shared_client import app as bot  # asbot — receives commands
from plugins.batch import UB          # per-user delivery bot set via /setbot (introvert)

print("[audiofix] plugin loaded, /audiofix command registered.")

AUDIOFIX_STATE = {}  # uid -> {'step': 'await_channel' | 'await_count'}
DOWNLOAD_DIR = "audiofix_downloads"

VIDEO_LIKE_EXTENSIONS = ('.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.ogv')

CODEC_TO_EXT = {
    "mp3": ".mp3",
    "aac": ".m4a",
    "opus": ".opus",
    "vorbis": ".ogg",
    "flac": ".flac",
    "wmav2": ".wma",
    "wmav1": ".wma",
    "pcm_s16le": ".wav",
    "alac": ".m4a",
}


async def has_video_stream(file_path: str) -> bool:
    """True if the local file actually contains a video stream."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error",
            "-select_streams", "v",
            "-show_entries", "stream=codec_type",
            "-of", "csv=p=0",
            file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return b"video" in stdout
    except Exception:
        return True  # if ffprobe itself fails, don't misclassify — skip as video


async def get_audio_codec(file_path: str) -> str | None:
    """Returns the audio codec name if the file has an audio stream, else None."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_name",
            "-of", "csv=p=0",
            file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        codec = stdout.decode(errors="ignore").strip()
        return codec or None
    except Exception:
        return None


@bot.on_message(filters.command("audiofix"), group=10)
async def audiofix_start(c: Client, m: Message):
    uid = m.from_user.id
    if uid not in UB:
        await m.reply_text("⚠️ Please set your delivery bot first with /setbot `token`.")
        return
    AUDIOFIX_STATE[uid] = {'step': 'await_channel'}
    await m.reply_text(
        "📡 Send the channel username (e.g. `@mychannel`) or channel ID "
        "(e.g. `-1001234567890`) to scan.\n\n"
        "Note: this bot must be an admin in that channel."
    )


@bot.on_message(filters.text & filters.private & ~filters.command([
    'start', 'help', 'login', 'logout', 'setbot', 'rembot', 'batch', 'single',
    'audiofix', 'plan', 'myplan', 'pay', 'terms', 'status', 'settings',
    'cancel', 'stop', 'add', 'rem', 'get', 'broadcast', 'stats', 'setbranding', 'set'
]), group=10)
async def audiofix_flow(c: Client, m: Message):
    uid = m.from_user.id
    if uid not in AUDIOFIX_STATE:
        return  # not in an /audiofix flow, let other handlers deal with it

    state = AUDIOFIX_STATE[uid]

    if state['step'] == 'await_channel':
        channel = m.text.strip()
        try:
            chat = await c.get_chat(channel)
        except Exception as e:
            await m.reply_text(f"❌ Couldn't access that channel: {e}\nMake sure the bot is an admin there, then send /audiofix again.")
            del AUDIOFIX_STATE[uid]
            return
        state['channel_id'] = chat.id
        state['channel_title'] = chat.title or channel
        state['step'] = 'await_count'
        await m.reply_text(f"✅ Found: {state['channel_title']}\nHow many recent messages should I scan? (e.g. 100)")
        return

    if state['step'] == 'await_count':
        if not m.text.strip().isdigit():
            await m.reply_text("Please send a number (e.g. 100).")
            return
        count = int(m.text.strip())
        del AUDIOFIX_STATE[uid]
        await run_audiofix(c, m, uid, state['channel_id'], state['channel_title'], count)
        return


async def run_audiofix(c: Client, m: Message, uid: int, channel_id, channel_title: str, count: int):
    status = await m.reply_text(f"🔍 Scanning last {count} messages in {channel_title} ...")

    delivery_bot = UB.get(uid)
    if not delivery_bot:
        await status.edit(f"⚠️ Please set your delivery bot first with /setbot `token`.")
        return

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    scanned = 0
    fixed = 0
    skipped_video = 0
    skipped_other = 0
    failed = 0

    try:
        async for msg in c.get_chat_history(channel_id, limit=count):
            scanned += 1

            if scanned % 10 == 0:
                try:
                    await status.edit(f"🔍 Scanning... {scanned}/{count} | Fixed: {fixed} | Skipped: {skipped_video + skipped_other}")
                except Exception:
                    pass

            media = msg.video or msg.document
            if not media:
                skipped_other += 1
                continue

            file_name = getattr(media, 'file_name', '') or ''
            file_ext = os.path.splitext(file_name)[1].lower()

            if not (msg.video or file_ext in VIDEO_LIKE_EXTENSIONS):
                skipped_other += 1
                continue

            local_path = os.path.join(DOWNLOAD_DIR, f"{uid}_{msg.id}_{int(time.time())}{file_ext or '.mp4'}")
            try:
                await c.download_media(msg, file_name=local_path)
            except Exception as e:
                failed += 1
                continue

            try:
                if await has_video_stream(local_path):
                    skipped_video += 1
                    os.remove(local_path)
                    continue

                codec = await get_audio_codec(local_path)
                if not codec:
                    skipped_other += 1
                    os.remove(local_path)
                    continue

                correct_ext = CODEC_TO_EXT.get(codec, ".mp3")
                fixed_path = os.path.splitext(local_path)[0] + correct_ext
                os.rename(local_path, fixed_path)

                await delivery_bot.send_audio(
                    uid,
                    audio=fixed_path,
                    caption=f"🎧 Fixed from: {file_name or 'unnamed'}",
                    file_name=os.path.basename(fixed_path),
                )
                fixed += 1
                os.remove(fixed_path)

            except Exception as e:
                failed += 1
                if os.path.exists(local_path):
                    os.remove(local_path)

    except Exception as e:
        await status.edit(f"❌ Error scanning channel: {e}")
        return

    await status.edit(
        "✅ **Audio-Fix Complete**\n\n"
        f"Scanned: {scanned}\n"
        f"🎧 Fixed & sent: {fixed}\n"
        f"⏭️ Skipped (genuine video): {skipped_video}\n"
        f"⏭️ Skipped (other/no audio): {skipped_other}\n"
        f"❌ Failed: {failed}"
    )
