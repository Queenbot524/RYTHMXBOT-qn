import asyncio
import json
import os
import re
import time

import requests
import yt_dlp
from lyricsgenius import Genius
from youtubesearchpython.__future__ import VideosSearch

from config import Config
from Music.core.clients import hellbot
from Music.core.logger import LOGS
from Music.helpers.strings import TEXTS
from Music.helpers.youtube import Hell_YTS


class YouTube:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        self.regex = r"(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:watch\?v=|embed\/|v\/|shorts\/)|youtu\.be\/|youtube\.com\/playlist\?list=)"
        self.audio_opts = {"format": "bestaudio[ext=m4a]"}
        self.video_opts = {
            "format": "best",
            "addmetadata": True,
            "key": "FFmpegMetadata",
            "prefer_ffmpeg": True,
            "geo_bypass": True,
            "nocheckcertificate": True,
            "postprocessors": [
                {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}
            ],
            "outtmpl": "%(id)s.mp4",
            "logtostderr": False,
            "quiet": True,
        }
        self.lyrics = Config.LYRICS_API
        try:
            if self.lyrics:
                self.client = Genius(self.lyrics, remove_section_headers=True)
            else:
                self.client = None
        except Exception as e:
            LOGS.warning(f"[Exception in Lyrics API]: {e}")
            self.client = None

    async def check(self, link: str):
        return bool(re.match(self.regex, link))

    async def format_link(self, link: str, video_id: bool) -> str:
        link = link.strip()
        if video_id:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        return link

    async def get_data(self, link: str, video_id: bool) -> dict:
        yt_url = await self.format_link(link, video_id)
        results = VideosSearch(yt_url, limit=1)
        for result in (await results.next())["result"]:
            vid = result["id"]
            channel = result["channel"]["name"]
            channel_url = result["channel"]["link"]
            description = result["descriptionSnippet"][0]["text"]
            duration = result["duration"]
            published = result["publishedTime"]
            thumbnail = f"https://i.ytimg.com/vi/{result['id']}/hqdefault.jpg"
            title = result["title"]
            url = result["link"]
            views = result["viewCount"]["short"]
        context = {
            "id": vid,
            "ch_link": channel_url,
            "channel": channel,
            "description": description,
            "duration": duration,
            "link": url,
            "published": published,
            "thumbnail": thumbnail,
            "title": title,
            "views": views,
        }
        return context

    async def download(self, link: str, video_id: bool):
        yt_url = await self.format_link(link, video_id)
        process = await asyncio.create_subprocess_exec(
            "yt-dlp",
            "-g",
            "-f",
            "best[height<=?720][width<=?1280]",
            f"{yt_url}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if stdout:
            return True, stdout.decode().split("\n")[0]
        else:
            return False, stderr.decode()

    async def get_tracks(self, mention, query: str) -> list:
        results = []
        try:
            output = json.loads(Hell_YTS(query, 10).to_json())
        except Exception as e:
            return results
        for i in output["videos"]:
            context = {
                "title": i["title"],
                "link": i["url_suffix"],
                "full_link": f"https://www.youtube.com{i['url_suffix']}",
                "vidid": i["id"],
                "views": i["views"],
                "duration": i["duration"],
                "thumb": f"https://i.ytimg.com/vi/{i['id']}/hqdefault.jpg",
                "mention": mention,
            }
            results.append(context)
        return results

    async def send_song(
        self, message, rand_key: str, key: int, video: bool = False
    ) -> dict:
        track = Config.SONG_CACHE[rand_key][key]
        ydl_opts = self.video_opts if video else self.audio_opts
        link = track["full_link"]
        hell = await message.reply_text("Downloading...")
        await message.delete()
        try:
            output = None
            thumb = f"{track['vidid']}{time.time()}.jpg"
            _thumb = requests.get(track["thumb"], allow_redirects=True)
            open(thumb, "wb").write(_thumb.content)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                yt_file = ydl.extract_info(link, download=video)
                if not video:
                    output = ydl.prepare_filename(yt_file)
                    ydl.process_info(yt_file)
                    await message.reply_audio(
                        audio=output,
                        caption=TEXTS.SONG_CAPTION.format(
                            track["title"],
                            link,
                            track["views"],
                            track["duration"],
                            track["mention"],
                            hellbot.app.mention,
                        ),
                        duration=int(yt_file["duration"]),
                        performer=TEXTS.PERFORMER,
                        title=yt_file["title"],
                        thumb=thumb,
                    )
                else:
                    output = f"{yt_file['id']}.mp4"
                    await message.reply_video(
                        video=output,
                        caption=TEXTS.SONG_CAPTION.format(
                            track["title"],
                            link,
                            track["views"],
                            track["duration"],
                            track["mention"],
                            hellbot.app.mention,
                        ),
                        duration=int(yt_file["duration"]),
                        thumb=thumb,
                        supports_streaming=True,
                    )
            chat = message.chat.title or message.chat.first_name
            await hellbot.logit(
                "Video" if video else "Audio",
                f"{track['mention']} uploaded a song named [{track['title']}]({link}) in {chat} (`{message.chat.id}`)",
            )
            await hell.delete()
        except Exception as e:
            await hell.edit_text(f"**Error:**\n`{e}`")
        try:
            Config.SONG_CACHE.pop(rand_key)
            os.remove(thumb)
            os.remove(output)
        except Exception:
            pass

    async def get_lyrics(self, song: str, artist: str) -> dict:
        context = {}
        if not self.client:
            return context
        results = self.client.search_song(song, artist)
        if results:
            results.to_dict()
            title = results["full_title"]
            image = results["song_art_image_url"]
            lyrics = results["lyrics"]
            context = {
                "title": title,
                "image": image,
                "lyrics": lyrics,
            }
        return context


ytube = YouTube()
