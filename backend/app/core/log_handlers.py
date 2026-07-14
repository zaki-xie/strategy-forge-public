# app/core/log_handlers.py
import os
import datetime
import glob
from logging import FileHandler

class DateBasedFileHandler(FileHandler):
    """
    按天自动切换日志文件。
    每次写入日志前检查日期，如果日期改变则关闭当前文件并打开新文件。
    文件名格式：base_filename.2026-06-07
    """
    def __init__(self, filename, mode='a', encoding=None, delay=False, backup_days=30):
        self.base_filename = filename          # 不带日期的原始路径，如 logs/app.log
        self._current_date = None
        self.backup_days = backup_days
        # 以今天的文件名打开（如 logs/app.log.2026-06-07）
        actual_filename = self._get_dated_filename()
        super().__init__(actual_filename, mode, encoding, delay)

    def _get_dated_filename(self, date=None):
        if date is None:
            date = datetime.date.today()
        base, ext = os.path.splitext(self.base_filename)
        return f"{base}.{date.strftime('%Y-%m-%d')}{ext}"


    def _clean_old_logs(self):
        """删除超过 backup_days 天的旧日志文件"""
        if self.backup_days <= 0:
            return
        base, ext = os.path.splitext(self.base_filename)
        pattern = f"{base}.*{ext}"
        files = sorted(glob.glob(pattern))
        cutoff = datetime.date.today() - datetime.timedelta(days=self.backup_days)
        for file_path in files:
            try:
                # 从文件名中提取日期，如 app.log.2026-06-07 -> 日期部分
                name = os.path.basename(file_path)
                date_str = name[len(base)+1 : -len(ext)]  # 去掉前缀和扩展名
                file_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                if file_date < cutoff:
                    os.remove(file_path)
            except (ValueError, OSError):
                pass   # 文件名无法解析或删除失败，跳过

    def emit(self, record):
        """每次记录日志时调用，检查是否需要切换文件"""
        today = datetime.date.today()
        if self._current_date != today:
            # 日期改变，关闭当前文件，打开新文件
            self._current_date = today
            self.close()
            self.baseFilename = self._get_dated_filename(today)
            self.stream = self._open()
            # ★ 每次跨天切换时顺便清理旧文件（也可以独立为一个定时任务）
            self._clean_old_logs()
        super().emit(record)
    