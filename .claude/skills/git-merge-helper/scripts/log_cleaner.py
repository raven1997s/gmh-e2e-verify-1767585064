#!/usr/bin/env python3
"""
Git Merge Helper - 日志清理器

功能：
- 自动清理过期的合并日志
- 保留策略：
  * 一周内最多保留 10 个日志
  * 一个月内最多保留 5 个日志
  * 超过一个月的全部删除

支持多种日志文件名格式：
  * merge-{source}-to-{target}-{timestamp}.log (新格式)
  * merge-batch-{count}branches-{timestamp}.log (批量合并)
  * merge_{timestamp}.log (旧格式)

Generated: 2026-01-04
"""

import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Tuple, Optional

# 导入 Git 工具类
try:
    from git_utils import GitRepository
except ImportError:
    # 如果无法导入，使用备用实现
    class GitRepository:
        DEFAULT_MAX_DEPTH = 50

        @staticmethod
        def find_root(start_dir=None, max_depth=None):
            if start_dir is None:
                start_dir = Path.cwd()
            if max_depth is None:
                max_depth = GitRepository.DEFAULT_MAX_DEPTH

            original_root = start_dir
            current = start_dir

            for _ in range(max_depth):
                if (current / ".git").exists():
                    return current
                if current.parent == current:
                    break
                current = current.parent

            raise RuntimeError(
                f"未找到 Git 仓库。\n"
                f"起始目录: {original_root}\n"
                f"最大深度: {max_depth}"
            )


class LogCleaner:
    """日志清理器"""

    # 新格式日志文件名: merge-[source]-to-[target]-YYYYMMDD-HHMMSS.log
    # 新格式批量: merge-batch-[count]branches-YYYYMMDD-HHMMSS.log
    # 旧格式日志文件名: merge_YYYYMMDD_HHMMSS.log
    LOG_PATTERNS = [
        # 新格式：merge-[source]-to-[target]-20260104-143000.log
        re.compile(r'merge-\[([^\]]+)\]-to-\[([^\]]+)\]-(\d{8})-(\d{6})\.log'),
        # 批量格式：merge-batch-[2branches]-20260104-143000.log
        re.compile(r'merge-batch-\[(\d+)branches\]-(\d{8})-(\d{6})\.log'),
        # 旧格式：merge_20260104_143000.log
        re.compile(r'merge_(\d{8})_(\d{6})\.log'),
    ]

    # 清理策略
    MAX_WEEK_LOGS = 10      # 一周内最多保留 10 个
    MAX_MONTH_LOGS = 5      # 一个月内最多保留 5 个
    WEEK_DAYS = 7           # 一周天数
    MONTH_DAYS = 30         # 一个月天数

    def __init__(self, logs_dir: Path):
        """
        初始化日志清理器

        Args:
            logs_dir: 日志目录路径
        """
        self.logs_dir = logs_dir
        self.cleaned_count = 0
        self.kept_count = 0

    def parse_log_file(self, filename: str) -> Tuple[Optional[datetime], str]:
        """
        解析日志文件名，提取时间戳

        Args:
            filename: 日志文件名

        Returns:
            (时间戳, 完整文件路径) 或 (None, filename)
        """
        full_path = self.logs_dir / filename

        # 尝试匹配所有日志格式
        for pattern in self.LOG_PATTERNS:
            match = pattern.search(filename)
            if match:
                try:
                    # 根据匹配的组提取日期和时间
                    # 旧格式和新格式的时间戳位置不同
                    groups = match.groups()
                    # 查找日期和时间组
                    date_str = None
                    time_str = None
                    for g in groups:
                        if g and len(g) == 8 and g.isdigit():  # 日期 YYYYMMDD
                            date_str = g
                        elif g and len(g) == 6 and g.isdigit():  # 时间 HHMMSS
                            time_str = g

                    if date_str and time_str:
                        timestamp = datetime.strptime(f"{date_str}{time_str}", "%Y%m%d%H%M%S")
                        return timestamp, str(full_path)
                except (ValueError, IndexError):
                    continue

        return None, filename

    def get_all_logs(self) -> List[Tuple[datetime, str]]:
        """
        获取所有有效的日志文件，按时间倒序排列

        Returns:
            [(时间戳, 文件路径), ...] 列表，按时间倒序
        """
        if not self.logs_dir.exists():
            return []

        logs = []
        for filename in os.listdir(self.logs_dir):
            timestamp, full_path = self.parse_log_file(filename)
            if timestamp and Path(full_path).exists():
                logs.append((timestamp, full_path))

        # 按时间倒序排列（最新的在前）
        logs.sort(key=lambda x: x[0], reverse=True)
        return logs

    def clean_logs(self, dry_run: bool = False) -> dict:
        """
        清理日志文件

        Args:
            dry_run: 是否为演习模式（不实际删除）

        Returns:
            清理结果统计
        """
        logs = self.get_all_logs()
        now = datetime.now()

        # 分类日志
        week_ago = now - timedelta(days=self.WEEK_DAYS)
        month_ago = now - timedelta(days=self.MONTH_DAYS)

        week_logs = [log for log in logs if log[0] > week_ago]
        month_logs = [log for log in logs if week_ago >= log[0] > month_ago]
        old_logs = [log for log in logs if log[0] <= month_ago]

        # 确定要删除的文件
        to_delete = []

        # 1. 一周内的日志：只保留最新的 MAX_WEEK_LOGS 个
        if len(week_logs) > self.MAX_WEEK_LOGS:
            to_delete.extend(week_logs[self.MAX_WEEK_LOGS:])

        # 2. 一个月内的日志：只保留最新的 MAX_MONTH_LOGS 个
        if len(month_logs) > self.MAX_MONTH_LOGS:
            to_delete.extend(month_logs[self.MAX_MONTH_LOGS:])

        # 3. 超过一个月的日志：全部删除
        to_delete.extend(old_logs)

        # 去重（按文件路径）
        to_delete_unique = []
        seen_paths = set()
        for log in to_delete:
            if log[1] not in seen_paths:
                to_delete_unique.append(log)
                seen_paths.add(log[1])

        # 执行删除
        self.cleaned_count = 0
        self.kept_count = len(logs) - len(to_delete_unique)

        for timestamp, filepath in to_delete_unique:
            if dry_run:
                print(f"[演习] 将删除: {Path(filepath).name} ({timestamp.strftime('%Y-%m-%d %H:%M:%S')})")
            else:
                try:
                    os.remove(filepath)
                    self.cleaned_count += 1
                except Exception as e:
                    print(f"⚠️  删除失败: {filepath} - {str(e)}")

        return {
            "total_logs": len(logs),
            "week_logs": len(week_logs),
            "month_logs": len(month_logs),
            "old_logs": len(old_logs),
            "cleaned": self.cleaned_count,
            "kept": self.kept_count,
            "dry_run": dry_run
        }

    def get_cleanup_summary(self) -> str:
        """
        获取清理策略说明

        Returns:
            清理策略文本
        """
        return f"""
📋 日志清理策略
{'=' * 40}

📌 保留规则:
  • 一周内 (7天): 最多保留 {self.MAX_WEEK_LOGS} 个日志
  • 一个月内 (30天): 最多保留 {self.MAX_MONTH_LOGS} 个日志
  • 超过一个月: 全部删除

📊 清理说明:
  • 日志按时间倒序排列，保留最新的
  • 超出数量限制的旧日志将被删除
  • 每次合并后自动执行清理

📁 日志位置: {self.logs_dir}

💡 提示:
  • 重要合并记录请及时备份
  • 日志文件包含详细的合并信息和冲突报告
"""


def clean_logs_after_merge(logs_dir: Path, verbose: bool = False) -> None:
    """
    合并后自动清理日志

    Args:
        logs_dir: 日志目录
        verbose: 是否显示详细信息
    """
    cleaner = LogCleaner(logs_dir)

    # 执行清理
    result = cleaner.clean_logs(dry_run=False)

    if verbose and result["cleaned"] > 0:
        print(f"\n🧹 已清理 {result['cleaned']} 个旧日志")
        print(f"📊 保留 {result['kept']} 个日志")


def main():
    """命令行入口（用于测试）"""
    import sys

    # 获取日志目录
    if len(sys.argv) > 1:
        logs_dir = Path(sys.argv[1])
    else:
        # 默认使用项目中的 logs 目录
        try:
            project_root = GitRepository.find_root()
            logs_dir = project_root / ".claude" / "logs"
        except RuntimeError as e:
            print(f"⚠️  {e}")
            print(f"   将使用当前目录的 .claude/logs/")
            logs_dir = Path.cwd() / ".claude" / "logs"

    cleaner = LogCleaner(logs_dir)

    # 显示策略
    print(cleaner.get_cleanup_summary())

    # 显示当前状态
    logs = cleaner.get_all_logs()
    print(f"\n当前日志数: {len(logs)}")

    if logs:
        print("\n最近的日志:")
        for i, (timestamp, filepath) in enumerate(logs[:5], 1):
            age = (datetime.now() - timestamp).days
            print(f"  {i}. {Path(filepath).name} ({age} 天前)")

    # 询问是否执行清理
    print("\n" + "-" * 40)
    response = input("是否执行清理? (y/n): ").strip().lower()

    if response == 'y':
        # 先演习
        print("\n演习模式 (不会实际删除):")
        cleaner.clean_logs(dry_run=True)

        print("\n" + "-" * 40)
        response = input("确认执行清理? (y/n): ").strip().lower()

        if response == 'y':
            result = cleaner.clean_logs(dry_run=False)
            print(f"\n✅ 清理完成!")
            print(f"   删除: {result['cleaned']} 个")
            print(f"   保留: {result['kept']} 个")
        else:
            print("已取消清理")
    else:
        print("已取消清理")


if __name__ == "__main__":
    main()
