import asyncio

from PyQt5.QtCore import QThread, pyqtSignal
import aiohttp


class HttpTaskManager(QThread):
    def __init__(self):
        super(HttpTaskManager, self).__init__()
        self.timeout = 20
        self._sem = None

    async def async_request(self, url):
        """异步任务"""
        if self._sem:
            async with self._sem:
                print('Getting data on url', url)
                return await self.fetch(url)
        else:
            print('Getting data on url', url)
            return await self.fetch(url)

    async def fetch(self, url):
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        while True:
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, ssl=False) as response:
                        content = await response.content.read()
                        return content
            except Exception as e:
                print(e)
                await asyncio.sleep(1)
                continue

    async def set_sem(self, thread_count):
        self._sem = asyncio.Semaphore(thread_count)  # 控制并发数
