#!/usr/bin/env python3
"""
Git Merge Helper - 日志记录器

功能：
- 记录合并操作的详细日志
- 支持多种日志级别
- 自动生成日志文件到 .claude/logs/ 目录
- 自动清理过期日志
- 生成包含分支信息的日志文件名

Generated: 2026-01-04
"""

import os
import sys
import platform
from datetime import datetime
from pathlib import Path
from typing import Optional
import urllib.parse

# 导入 Git 工具类
try:
    from git_utils import GitRepository
except ImportError:
    # 如果无法导入，使用备用实现
    class GitRepository:
        DEFAULT_MAX_DEPTH = 50

        @staticmethod
        def find_root(start_dir=None, max_depth=None):
            from pathlib import Path
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

# 导入日志清理器
try:
    from log_cleaner import clean_logs_after_merge
except ImportError:
    # 如果无法导入，定义一个空函数
    def clean_logs_after_merge(*args, **kwargs):
        pass


class MergeLogger:
    """合并日志记录器"""

    def __init__(self, project_root: Optional[Path] = None):
        """
        初始化日志记录器

        Args:
            project_root: 项目根目录，默认为当前目录向上查找 Git 仓库

        Raises:
            RuntimeError: 如果未找到 Git 仓库或无权限创建日志目录
        """
        if project_root is None:
            # 使用共享的 Git 仓库查找逻辑
            project_root = GitRepository.find_root()

        self.project_root = project_root
        self.logs_dir = project_root / ".claude" / "logs"

        # 检查并创建日志目录，处理权限问题
        try:
            self.logs_dir.mkdir(parents=True, exist_ok=True)

            # 验证目录是否可写
            test_file = self.logs_dir / ".write_test"
            try:
                test_file.touch()
                test_file.unlink()
            except PermissionError:
                raise RuntimeError(
                    f"日志目录无写入权限: {self.logs_dir}\n"
                    f"请检查目录权限或使用 --log-dir 参数指定其他位置"
                )
        except PermissionError as e:
            # 尝试使用临时目录
            import tempfile
            import os
            temp_base = Path(tempfile.gettempdir())
            self.logs_dir = temp_base / ".claude" / "logs"

            try:
                self.logs_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e2:
                raise RuntimeError(
                    f"无法创建日志目录。\n"
                    f"项目目录: {project_root / '.claude' / 'logs'} - {e}\n"
                    f"临时目录: {self.logs_dir} - {e2}\n"
                    f"请检查文件系统权限"
                )

        # 日志文件（在设置分支信息后生成）
        self.log_file = None

        # 合并信息
        self.current_branch = ""
        self.target_branch = ""
        self.target_branches = []  # 批量合并时的目标分支列表
        self.temp_branch = ""
        self.start_time = datetime.now()
        self.steps = []

        # 标记是否为批量合并
        self.is_batch_merge = False

    def _sanitize_branch_name(self, branch_name: str) -> str:
        """
        清理分支名，移除或替换特殊字符

        Args:
            branch_name: 原始分支名

        Returns:
            清理后的分支名
        """
        # 替换 / 为 -
        # 移除其他特殊字符
        sanitized = branch_name.replace("/", "-").replace("\\", "-")
        # 只保留字母、数字、连字符、下划线和点
        sanitized = "".join(c if c.isalnum() or c in "-_." else "" for c in sanitized)
        return sanitized

    def _generate_log_filename(self) -> Path:
        """
        生成日志文件名

        Returns:
            日志文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        if self.is_batch_merge and self.target_branches:
            # 批量合并：merge-batch-[count]-{timestamp}.log
            count = len(self.target_branches)
            filename = f"merge-batch-[{count}branches]-{timestamp}.log"
        elif self.current_branch and self.target_branch:
            # 单分支合并：merge-[source]-to-[target]-{timestamp}.log
            source = self._sanitize_branch_name(self.current_branch)
            target = self._sanitize_branch_name(self.target_branch)
            filename = f"merge-[{source}]-to-[{target}]-{timestamp}.log"
        else:
            # 默认格式
            filename = f"merge-{timestamp}.log"

        return self.logs_dir / filename

    def ensure_log_file(self):
        """确保日志文件已创建"""
        if self.log_file is None:
            self.log_file = self._generate_log_filename()

    def log(self, level: str, message: str, details: str = ""):
        """
        记录日志

        Args:
            level: 日志级别 (INFO, SUCCESS, WARNING, ERROR)
            message: 日志消息
            details: 详细信息（可选）
        """
        timestamp = datetime.now().strftime("[%H:%M:%S.%f")[:-3]
        icon = {
            "INFO": "✓",
            "SUCCESS": "✅",
            "WARNING": "⚠️ ",
            "ERROR": "✗"
        }.get(level, "•")

        log_entry = f"{timestamp} {icon} {message}"
        if details:
            log_entry += f"\n  > {details}"

        self.steps.append(log_entry)
        
        # 实时打印到控制台
        print(log_entry)

    def set_branches(self, current: str, target: str, temp: str = ""):
        """设置分支信息"""
        self.current_branch = current
        self.target_branch = target
        self.temp_branch = temp

    def set_batch_merge(self, target_branches: list):
        """设置为批量合并模式"""
        self.is_batch_merge = True
        self.target_branches = target_branches

    def set_result(self, status: str, reason: str = ""):
        """设置合并结果"""
        self.status = status
        self.reason = reason

    def get_log_link(self) -> str:
        """
        获取可点击的日志文件链接

        Returns:
            可点击的链接字符串
        """
        self.ensure_log_file()
        if self.log_file is None:
            return ""

        abs_path = self.log_file.resolve()

        # macOS 和大多数现代终端支持 file:// 协议
        # 直接返回文件路径，大多数终端可以 Cmd+Click 打开
        return str(abs_path)

    def print_log_link(self):
        """打印可点击的日志链接"""
        self.ensure_log_file()
        if self.log_file is None:
            return

        filename = self.log_file.name
        # 使用相对于项目根目录的路径
        try:
            rel_path = self.log_file.relative_to(self.project_root)
        except ValueError:
            # 如果无法计算相对路径，使用文件名
            rel_path = filename

        print(f"\n{'='*60}")
        print(f"📝 日志已保存")
        print(f"   文件名: {filename}")
        print(f"   路径: {rel_path}")
        print(f"{'='*60}")
        print(f"💡 提示: Cmd+Click (macOS) 或 Ctrl+Click (Linux/Windows) 可打开文件")
        print()

    def save(self):
        """保存日志到文件"""
        # 确保日志文件已生成
        self.ensure_log_file()

        if self.log_file is None:
            return None

        duration = (datetime.now() - self.start_time).total_seconds()

        content = f"""合并日志 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
{'='*60}
当前分支:    {self.current_branch}"""

        if self.is_batch_merge and self.target_branches:
            content += f"\n目标分支:    {', '.join(self.target_branches)}"
        else:
            content += f"\n目标分支:    {self.target_branch}"

        if self.temp_branch:
            content += f"\n临时分支:    {self.temp_branch}"
        content += f"\n状态:        {self.status}"
        if self.reason:
            content += f"\n原因:        {self.reason}"
        content += f"\n耗时:        {duration:.2f} seconds"

        content += "\n\n操作步骤：\n"
        for step in self.steps:
            content += f"{step}\n"

        # 写入文件
        with open(self.log_file, "w", encoding="utf-8") as f:
            f.write(content)

        # 自动清理过期日志
        try:
            clean_logs_after_merge(self.logs_dir, verbose=False)
        except Exception as e:
            # 清理失败不影响日志保存
            pass

        return self.log_file


def main():
    """命令行入口（用于测试）"""
    logger = MergeLogger()
    logger.set_branches("feature/test", "test", "merge-123")
    logger.log("INFO", "检查环境", "工作目录干净")
    logger.log("INFO", "创建临时分支", "merge-feature-test-123")
    logger.log("SUCCESS", "合并成功", "4 个文件已更改")
    logger.set_result("SUCCESS")
    log_file = logger.save()
    print(f"日志已保存到: {log_file}")


if __name__ == "__main__":
    main()
