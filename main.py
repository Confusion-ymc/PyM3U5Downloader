import asyncio
import os
import sys
import time
import platform
from pathlib import Path
from PyQt5.QtCore import pyqtSignal, QObject, QThread

from http_helper import HttpTaskManager
from m3u8_helper import M3u8File

from PyQt5 import QtWidgets

from ui import Ui_Form

from quamash import QEventLoop


# https://v10.dious.cc/20210917/fbTKMtck/1000kb/hls/index.m3u8

class Runner(QThread):
    progress_signal = pyqtSignal()
    progress_max_signal = pyqtSignal(int)
    log_signal = pyqtSignal(str)
    reset_bar_signal = pyqtSignal()
    run_state = pyqtSignal(bool)

    def __init__(self, m3u8_file: M3u8File = None, temp_dir: Path = None, out_dir: Path = None,
                 thread_count: int = None, save_name: str = None):
        super(Runner, self).__init__()
        self.m3u8_file = m3u8_file
        self.temp_dir: Path = temp_dir
        self.out_dir = out_dir
        self.thread_count = thread_count
        self.save_name = save_name
        self.http_manager = HttpTaskManager()

    def set_config(self, m3u8_file: M3u8File, temp_dir, out_dir, thread_count, save_name):
        self.m3u8_file = m3u8_file
        self.temp_dir: Path = temp_dir
        self.out_dir = out_dir
        self.thread_count = thread_count
        self.save_name = save_name

    async def requests_and_save(self, segment):
        content = await self.http_manager.async_request(segment.absolute_uri)
        self.save_content(segment, content)

    def save_content(self, segment, content):
        file_name = segment.absolute_uri.split('/')[-1]
        key = segment.key
        if key:
            decode_content = key.decrypt(content)
        else:
            decode_content = content
        try:
            with open(self.temp_dir / file_name, 'wb') as fd:
                fd.write(decode_content)
            self.progress_signal.emit()
            self.log_signal.emit(f'save {file_name}')
        except Exception as e:
            print(f"failed {file_name} {e}")
            self.log_signal.emit(f'failed {file_name} {e}')

    def contact_files(self):
        self.log_signal.emit('contact ts...')
        if platform.system() == 'Windows':
            print('Windows系统')
            cmd = fr'.\lib\bin\ffmpeg.exe -i .\m3u8_temp\index.m3u8 -c copy {str(self.out_dir / (self.save_name or "out.mp4"))}'
        else:
            cmd = f'ffmpeg -safe 0 -i {str(self.temp_dir / "index.m3u8")} -c copy {str(self.out_dir / (self.save_name or "out.mp4"))}'
        # ffmpeg 合并
        os.system(cmd)
        # self.log_signal.emit('contact files')
        # self.reset_bar_signal.emit()
        # with open(str(self.out_dir / (self.save_name or 'out.mp4')), 'wb+') as f:
        #     for segment in self.m3u8_file.playlist.segments:
        #         file_name = segment.absolute_uri.split('/')[-1]
        #         with open(self.temp_dir / file_name, 'rb') as son_data:
        #             while True:
        #                 decode_data = son_data.read(1024)
        #                 if decode_data:
        #                     f.write(decode_data)
        #                 else:
        #                     break
        #         self.progress_signal.emit()
        #     f.flush()

    async def async_run(self):
        self.run_state.emit(False)
        self.log_signal.emit('解析中...')
        try:
            await self.m3u8_file.analysis()
            self.log_signal.emit('解析成功!')
            self.progress_max_signal.emit(len(self.m3u8_file.playlist.segments))
        except Exception as e:
            print(e)
            self.log_signal.emit('解析失败')
            self.run_state.emit(True)
            return

        # 设置并发控制器
        await self.http_manager.set_sem(self.thread_count)
        tasks = []
        for segment in self.m3u8_file.playlist.segments:
            self.m3u8_file.check_url(segment)
            file_name = segment.absolute_uri.split('/')[-1]
            if (Path().cwd() / self.temp_dir / file_name).is_file():
                self.progress_signal.emit()
                self.log_signal.emit(f'{file_name} 存在 已跳过')
                continue
            else:
                task = asyncio.create_task(self.requests_and_save(segment))
                tasks.append(task)
        await asyncio.gather(*tasks)
        self.log_signal.emit('download finish!')
        time.sleep(1)
        self.contact_files()
        self.clear()
        self.log_signal.emit('all finish !')
        self.run_state.emit(True)

    def run(self):
        asyncio.run(self.async_run())

    def clear(self):
        self.reset_bar_signal.emit()
        for segment in self.m3u8_file.playlist.segments:
            file_name = segment.absolute_uri.split('/')[-1]
            if (self.temp_dir / file_name).is_file():
                os.remove(self.temp_dir / file_name)
                self.progress_signal.emit()
                self.log_signal.emit(f'清理：{file_name}')
        file_name = 'index.m3u8'
        os.remove(self.temp_dir / file_name)
        self.log_signal.emit(f'清理：{file_name}')


class MyDownloadUi(Ui_Form, QObject):
    progress_signal = pyqtSignal()
    log_signal = pyqtSignal(str)

    def __init__(self, form):
        super(MyDownloadUi, self).__init__()
        self.title = 'M3U8下载器V2'
        form.setWindowTitle(self.title)
        self.setupUi(form)
        self.is_start = False
        self.m3u8_file = None
        self.temp_dir = Path().cwd() / 'm3u8_temp'
        self.out_dir = Path().cwd() / 'm3u8_output'
        self.finish_count = 0
        self.all_task_count = 0
        self.init_dir()
        self.runner = Runner()
        self.url_input.setFocus()
        self.set_connect()

    def start_btn(self, flag):
        if not flag:
            self.startButton.setText('下载中')
        else:
            self.startButton.setText('开始')
        self.startButton.setEnabled(flag)

    def set_finish_count(self):
        self.finish_count = 0

    def set_progressbar(self):
        self.finish_count += 1
        self.progressBar.setValue(self.finish_count)
        self.progress_text.setText('{}/{}'.format(self.finish_count, self.all_task_count))

    def set_progressbar_max(self, length):
        self.all_task_count = length
        self.progressBar.setMaximum(length)

    def set_log(self, text):
        self.detail_label.setText(text)

    def init_dir(self):
        if not self.temp_dir.is_dir():
            self.temp_dir.mkdir()
            print(self.temp_dir, '已创建')
        if not self.out_dir.is_dir():
            self.out_dir.mkdir()
            print(self.out_dir, '已创建')

    def set_connect(self):
        # 按钮
        self.startButton.clicked.connect(self.start_btn_click)
        self.open_folderButton.clicked.connect(self.open_folder_btn_click)
        # 信号
        self.runner.reset_bar_signal.connect(self.set_finish_count)
        self.runner.log_signal.connect(self.set_log)
        self.runner.run_state.connect(self.start_btn)
        self.runner.progress_signal.connect(self.set_progressbar)
        self.runner.progress_max_signal.connect(self.set_progressbar_max)
        self.log_signal.connect(self.set_log)
        self.progress_signal.connect(self.set_progressbar)

    def start_btn_click(self):
        self.finish_count = 0
        self.m3u8_file = M3u8File(self.url_input.text(), self.temp_dir)
        self.runner.set_config(
            m3u8_file=self.m3u8_file,
            temp_dir=self.temp_dir,
            out_dir=self.out_dir,
            thread_count=self.thread_count.value(),
            save_name=self.file_name.text()
        )
        self.runner.start()

    def open_folder_btn_click(self):
        path = Path().cwd() / self.out_dir
        try:
            # windows
            os.startfile(path)
        except:
            # mac
            os.system("open {}".format(path))


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    Form = QtWidgets.QWidget()
    main_ui = MyDownloadUi(Form)
    Form.show()
    sys.exit(app.exec_())
