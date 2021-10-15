import asyncio
import copy
from typing import Optional

from m3u8 import M3U8

from http_helper import HttpTaskManager

try:
    from Crypto.Cipher import AES
except ImportError:
    from Cryptodome.Cipher import AES

from Crypto.Util.Padding import pad
import m3u8


class M3u8File:
    def __init__(self, url, temp_dir):
        self.url = url
        self.file_content = None
        self.method = None
        self.key_map = {}
        self.temp_dir = temp_dir
        self.http_manager = HttpTaskManager()
        self.mode_map = {
            'AES-128': AES.MODE_CBC
        }
        self.url_to_key = {}
        self.domain = '/'.join(url.split("/")[:3]) + '/'
        self.playlist: M3U8 = Optional[None]

    def decrypt_content(self, segment):
        if segment.key:
            return segment.key.decrypt(segment.content)
        else:
            return segment.content
        # if self.crypto:
        #     try:
        #         content = self.crypto.decrypt(content)
        #     except ValueError:
        #         content = pad(content, 16, style='pkcs7')
        #         content = self.crypto.decrypt(content)
        #     return content
        # else:
        #     return content

    async def analysis(self):
        from urllib.parse import urlparse
        while True:
            # 下载m3u8文件
            res = await self.http_manager.async_request(self.url)
            print('M3U8下载成功')
            print('开始解析')
            self.playlist = m3u8.loads(res.decode())
            if len(self.playlist.playlists) and self.playlist.playlists[0].uri.endswith('.m3u8'):
                parsed_url = urlparse(self.url)
                self.url = parsed_url.scheme + '://' + parsed_url[1] + self.playlist.playlists[0].uri
            else:
                break
        self.save_index_file()
        for key in self.playlist.keys:
            if not key or key.method == 'NONE':
                continue
            key_content = await self.http_manager.async_request(key.absolute_uri)
            self.key_map[key.absolute_uri] = AES.new(
                key_content, self.mode_map[self.playlist.keys[0].method],
                key.iv.replace("0x", "")[:16].encode()
            ) if key.iv else AES.new(
                key_content, self.mode_map[self.playlist.keys[0].method]
            )
        for segment in self.playlist.segments:
            if not segment.key or segment.key.method == 'NONE':
                segment.key = None
            else:
                segment.key = self.key_map[segment.key.absolute_uri]
        print('解析完成')

    def save_index_file(self):
        # 保存m3u8文件用于 ffmpeg合并
        copy_file = copy.deepcopy(self.playlist)
        for item in copy_file.segments:
            item.uri = item.uri.split('/')[-1]
            item.key = None
        copy_file.dump(self.temp_dir / 'index.m3u8')


if __name__ == '__main__':
    from pathlib import Path

    temp_dir = Path().cwd() / 'm3u8_temp'
    m3u8_file = M3u8File('https://v10.dious.cc/20210917/fbTKMtck/1000kb/hls/index.m3u8', temp_dir)
    asyncio.run(m3u8_file.analysis())
