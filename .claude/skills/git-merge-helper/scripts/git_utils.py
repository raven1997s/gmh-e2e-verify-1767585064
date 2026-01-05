#!/usr/bin/env python3
"""
Git Merge Helper - Git 工具类

功能：
- 统一的 Git 仓库查找逻辑
- 跨平台的文件锁实现
- 远程仓库名称检测
- Git 命令辅助函数

Generated: 2026-01-04
"""

import os
import sys
import platform
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional, Tuple


# ==================== 平台检测 ====================
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"
IS_MACOS = platform.system() == "Darwin"


# ==================== Git 仓库查找 ====================
class GitRepository:
    """Git 仓库工具类"""

    # 默认最大遍历深度
    DEFAULT_MAX_DEPTH = 50

    @staticmethod
    def find_root(start_dir: Optional[Path] = None, max_depth: int = None) -> Path:
        """
        查找 Git 仓库根目录

        Args:
            start_dir: 起始目录，默认为当前目录
            max_depth: 最大遍历深度，默认为 DEFAULT_MAX_DEPTH

        Returns:
            Git 仓库根目录路径

        Raises:
            RuntimeError: 如果未找到 Git 仓库
        """
        if start_dir is None:
            start_dir = Path.cwd()

        if max_depth is None:
            max_depth = GitRepository.DEFAULT_MAX_DEPTH

        original_root = start_dir
        current = start_dir

        # 向上查找 Git 仓库根目录
        for _ in range(max_depth):
            if (current / ".git").exists():
                return current

            # 检查是否到达文件系统根目录
            if current.parent == current:
                break

            current = current.parent

        # 未找到 Git 仓库
        raise RuntimeError(
            f"未找到 Git 仓库。\n"
            f"起始目录: {original_root}\n"
            f"最大深度: {max_depth}"
        )

    @staticmethod
    def find_root_safe(start_dir: Optional[Path] = None, max_depth: int = None) -> Optional[Path]:
        """
        查找 Git 仓库根目录（安全版本，不抛出异常）

        Args:
            start_dir: 起始目录，默认为当前目录
            max_depth: 最大遍历深度

        Returns:
            Git 仓库根目录路径，如果未找到则返回 None
        """
        try:
            return GitRepository.find_root(start_dir, max_depth)
        except RuntimeError:
            return None

    @staticmethod
    def is_inside_repo() -> bool:
        """
        检查当前目录是否在 Git 仓库中

        Returns:
            是否在 Git 仓库中
        """
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False
        )
        return result.returncode == 0 and result.stdout.strip() == "true"

    @staticmethod
    def get_logs_dir(start_dir: Optional[Path] = None) -> Path:
        """
        获取日志目录路径

        Args:
            start_dir: 起始目录

        Returns:
            日志目录路径

        Raises:
            RuntimeError: 如果未找到 Git 仓库
        """
        repo_root = GitRepository.find_root(start_dir)
        return repo_root / ".claude" / "logs"


# ==================== 远程仓库检测 ====================
class GitRemote:
    """Git 远程仓库工具类（线程安全）"""

    _remote_name_cache: Optional[str] = None
    _cache_lock = threading.Lock()  # 线程安全锁

    @staticmethod
    def get_remote_name() -> str:
        """
        自动检测远程仓库名称（线程安全）

        Returns:
            远程仓库名称，默认为 'origin'

        Note:
            结果会被缓存，多次调用只执行一次检测
            使用锁保证多线程环境下的安全性
        """
        # 先检查缓存（不加锁，快速路径）
        if GitRemote._remote_name_cache is not None:
            return GitRemote._remote_name_cache

        # 缓存未命中，加锁检测
        with GitRemote._cache_lock:
            # 双重检查：可能在等待锁时其他线程已经设置了缓存
            if GitRemote._remote_name_cache is not None:
                return GitRemote._remote_name_cache

            # 执行远程名称检测
            detected = None
            try:
                result = subprocess.run(
                    ["git", "remote", "show"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10
                )
                if result.returncode == 0 and result.stdout.strip():
                    remotes = result.stdout.strip().split("\n")
                    if remotes:
                        detected = remotes[0].strip()
            except (subprocess.TimeoutExpired, OSError):
                # 超时或系统错误，使用默认值
                pass

            # 设置缓存（在锁内）
            GitRemote._remote_name_cache = detected if detected else "origin"
            return GitRemote._remote_name_cache

    @staticmethod
    def clear_cache():
        """清除远程名称缓存（线程安全）"""
        with GitRemote._cache_lock:
            GitRemote._remote_name_cache = None

    @staticmethod
    def get_all_remotes() -> Tuple[str, ...]:
        """
        获取所有远程仓库名称

        Returns:
            远程仓库名称元组
        """
        try:
            result = subprocess.run(
                ["git", "remote"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                remotes = result.stdout.strip().split("\n")
                return tuple(r.strip() for r in remotes if r.strip())
        except (subprocess.TimeoutExpired, OSError):
            # 超时或系统错误，返回空元组
            pass
        return ()


# ==================== 跨平台文件锁 ====================
class FileLock:
    """
    跨平台文件锁

    Unix/Linux: 使用 fcntl
    Windows: 使用 msvcrt.locking
    """

    def __init__(self, lock_path: Path):
        """
        初始化文件锁

        Args:
            lock_path: 锁文件路径
        """
        self.lock_path = lock_path
        self.lock_file = None
        self._is_locked = False

    def acquire(self, blocking: bool = False) -> bool:
        """
        获取文件锁

        Args:
            blocking: 是否阻塞等待

        Returns:
            是否成功获取锁
        """
        # 确保锁文件目录存在
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # 尝试创建锁文件
            if IS_WINDOWS:
                return self._acquire_windows(blocking)
            else:
                return self._acquire_unix(blocking)
        except (IOError, OSError):
            return False

    def _acquire_unix(self, blocking: bool) -> bool:
        """Unix/Linux 平台获取锁（使用 fcntl）"""
        import fcntl

        try:
            # 原子性创建文件
            try:
                self.lock_file = open(self.lock_path, 'x')
            except FileExistsError:
                self.lock_file = open(self.lock_path, 'r')

            # 获取锁
            lock_type = fcntl.LOCK_EX
            if not blocking:
                lock_type |= fcntl.LOCK_NB

            fcntl.flock(self.lock_file.fileno(), lock_type)
            self._is_locked = True
            return True
        except (IOError, OSError):
            if self.lock_file:
                try:
                    self.lock_file.close()
                except Exception:
                    pass
                self.lock_file = None
            return False

    def _acquire_windows(self, blocking: bool) -> bool:
        """
        Windows 平台获取锁（使用 msvcrt）

        支持 blocking 参数：
        - blocking=False: 非阻塞，立即返回
        - blocking=True: 阻塞等待，最多等待 10 秒
        """
        import msvcrt
        import os

        mode = os.O_RDWR | os.O_CREAT
        max_wait_seconds = 10  # 阻塞模式下最多等待 10 秒
        retry_interval = 0.1   # 重试间隔 100ms

        start_time = time.time()

        while True:
            try:
                # 打开文件
                fd = os.open(self.lock_path, mode, 0o666)

                try:
                    # 尝试非阻塞锁定
                    # LK_NBLCK = 非阻塞排他锁
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    # 锁定成功
                    self.lock_file = os.fdopen(fd, 'w')
                    self._is_locked = True
                    return True

                except OSError:
                    # 锁定失败（文件已被锁定）
                    os.close(fd)

                    if not blocking:
                        # 非阻塞模式：立即返回失败
                        return False

                    # 阻塞模式：检查是否超时
                    if time.time() - start_time >= max_wait_seconds:
                        return False

                    # 等待后重试
                    time.sleep(retry_interval)
                    continue

            except (IOError, OSError) as e:
                # 打开文件失败
                if not blocking:
                    return False

                # 阻塞模式：检查是否超时
                if time.time() - start_time >= max_wait_seconds:
                    return False

                time.sleep(retry_interval)

    def release(self):
        """释放文件锁"""
        if not self._is_locked:
            return

        if self.lock_file:
            try:
                if IS_WINDOWS:
                    import msvcrt
                    fd = self.lock_file.fileno()
                    # 解锁
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass  # 忽略释放锁时的错误
            finally:
                try:
                    self.lock_file.close()
                except Exception:
                    pass
                self.lock_file = None

        self._is_locked = False

    def __enter__(self):
        """支持 with 语句"""
        self.acquire(blocking=True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持 with 语句"""
        self.release()

    def __del__(self):
        """析构时释放锁"""
        self.release()


# ==================== Git 命令辅助 ====================
class GitCommand:
    """Git 命令辅助类"""

    @staticmethod
    def run(args: list, check: bool = True, cwd: Optional[Path] = None,
             timeout: Optional[int] = None) -> subprocess.CompletedProcess:
        """
        执行 Git 命令

        Args:
            args: 命令参数列表
            check: 是否检查返回码
            cwd: 工作目录
            timeout: 超时时间（秒）

        Returns:
            subprocess.CompletedProcess 对象
        """
        cmd = ["git"] + args
        kwargs = {
            "capture_output": True,
            "text": True,
            "check": check
        }

        if cwd is not None:
            kwargs["cwd"] = str(cwd)
        if timeout is not None:
            kwargs["timeout"] = timeout

        return subprocess.run(cmd, **kwargs)


def main():
    """命令行入口（用于测试）"""
    print("Git 工具类测试")
    print("=" * 50)

    # 测试平台检测
    print(f"\n平台检测:")
    print(f"  Windows: {IS_WINDOWS}")
    print(f"  Linux: {IS_LINUX}")
    print(f"  macOS: {IS_MACOS}")

    # 测试 Git 仓库查找
    print(f"\nGit 仓库查找:")
    try:
        repo_root = GitRepository.find_root()
        print(f"  ✓ 仓库根目录: {repo_root}")
    except RuntimeError as e:
        print(f"  ✗ {e}")

    # 测试远程仓库检测
    print(f"\n远程仓库检测:")
    remote = GitRemote.get_remote_name()
    print(f"  ✓ 远程名称: {remote}")
    print(f"  ✓ 所有远程: {GitRemote.get_all_remotes()}")

    # 测试日志目录
    print(f"\n日志目录:")
    try:
        logs_dir = GitRepository.get_logs_dir()
        print(f"  ✓ 日志目录: {logs_dir}")
    except RuntimeError as e:
        print(f"  ✗ {e}")

    # 测试文件锁
    print(f"\n文件锁测试:")
    lock_path = Path("/tmp/test_merge.lock") if not IS_WINDOWS else Path("C:\\temp\\test_merge.lock")
    lock = FileLock(lock_path)
    if lock.acquire(blocking=False):
        print(f"  ✓ 成功获取锁")
        lock.release()
        print(f"  ✓ 成功释放锁")
    else:
        print(f"  ✗ 获取锁失败（可能已被占用）")


if __name__ == "__main__":
    main()
