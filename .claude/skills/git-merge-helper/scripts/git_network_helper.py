#!/usr/bin/env python3
"""
Git Merge Helper - 网络操作辅助类

功能：
- Git 命令重试机制（可配置重试次数）
- 远程分支检查（存在性、权限）
- 支持自定义远程名称
- 详细的错误日志

Generated: 2026-01-04
"""

import subprocess
import time
from dataclasses import dataclass
from typing import List, Optional, Callable, TYPE_CHECKING
from enum import Enum

# 避免循环导入
if TYPE_CHECKING:
    from config import MergeConfig


class NetworkError(Enum):
    """网络错误类型"""
    TIMEOUT = "timeout"
    CONNECTION_REFUSED = "connection_refused"
    HOST_NOT_FOUND = "host_not_found"
    PERMISSION_DENIED = "permission_denied"
    BRANCH_NOT_FOUND = "branch_not_found"
    UNKNOWN = "unknown"


@dataclass
class GitOperationResult:
    """Git 操作结果"""
    success: bool
    command: str
    stdout: str
    stderr: str
    returncode: int
    retries: int
    error_type: Optional[NetworkError] = None
    error_message: Optional[str] = None


class GitNetworkHelper:
    """Git 网络操作辅助类"""

    # 默认网络错误关键词
    NETWORK_ERROR_KEYWORDS = [
        "timeout",
        "timed out",
        "connection refused",
        "could not connect",
        "host not found",
        "network unreachable",
        "unable to access",
        "ssl error",
        "certificate",
        "permission denied",
        "could not read from remote",
        # 扩展的错误关键词
        "dns error",
        "name resolution failed",
        "no route to host",
        "network is unreachable",
        "ssl",
        "tls",
        "handshake",
        "connection reset",
        "connection timed out",
        "temporary failure",
    ]

    def __init__(self, logger=None, config=None):
        """
        初始化网络辅助类

        Args:
            logger: 日志记录器（可选）
            config: 配置对象（可选）
        """
        self.logger = logger

        # 从配置或使用默认值
        if config:
            self.max_retries = config.max_retries
            self.retry_delay = config.retry_delay
            self.network_timeout = config.network_timeout
        else:
            self.max_retries = 3
            self.retry_delay = 2
            self.network_timeout = 30

    def _is_network_error(self, error_output: str) -> bool:
        """
        判断是否为网络错误

        Args:
            error_output: 错误输出

        Returns:
            是否为网络错误
        """
        error_lower = error_output.lower()
        return any(keyword in error_lower for keyword in self.NETWORK_ERROR_KEYWORDS)

    def _detect_error_type(self, error_output: str) -> NetworkError:
        """
        检测错误类型

        Args:
            error_output: 错误输出

        Returns:
            错误类型
        """
        error_lower = error_output.lower()

        if "timeout" in error_lower or "timed out" in error_lower:
            return NetworkError.TIMEOUT
        elif "connection refused" in error_lower:
            return NetworkError.CONNECTION_REFUSED
        elif "host not found" in error_lower:
            return NetworkError.HOST_NOT_FOUND
        elif "permission denied" in error_lower:
            return NetworkError.PERMISSION_DENIED
        else:
            return NetworkError.UNKNOWN

    def run_git_with_retry(
        self,
        args: List[str],
        operation_name: str = "Git 操作",
        timeout: Optional[int] = None,
        check_remote: bool = False
    ) -> GitOperationResult:
        """
        执行 Git 命令，支持重试

        Args:
            args: 命令参数列表
            operation_name: 操作名称（用于日志）
            timeout: 超时时间（秒）
            check_remote: 是否检查远程连接

        Returns:
            操作结果
        """
        if timeout is None:
            timeout = self.network_timeout

        command_str = "git " + " ".join(args)
        retries = 0
        last_error = None

        while retries <= self.max_retries:
            try:
                # 执行命令
                process = subprocess.run(
                    ["git"] + args,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=timeout
                )

                # 成功
                if process.returncode == 0:
                    result = GitOperationResult(
                        success=True,
                        command=command_str,
                        stdout=process.stdout,
                        stderr=process.stderr,
                        returncode=process.returncode,
                        retries=retries
                    )

                    if retries > 0 and self.logger:
                        self.logger.log(
                            "INFO",
                            f"{operation_name} 重试成功",
                            f"第 {retries + 1} 次尝试成功"
                        )

                    return result

                # 失败，检查是否为网络错误
                error_output = process.stderr + process.stdout

                if self._is_network_error(error_output):
                    last_error = self._detect_error_type(error_output)

                    if retries < self.max_retries:
                        retries += 1
                        wait_time = self.retry_delay * retries  # 递增延迟

                        if self.logger:
                            self.logger.log(
                                "WARNING",
                                f"{operation_name} 失败，{wait_time}秒后重试",
                                f"尝试 {retries + 1}/{self.max_retries + 1}: {last_error.value}"
                            )

                        time.sleep(wait_time)
                        continue
                    else:
                        # 达到最大重试次数
                        error_message = self._format_error_message(operation_name, last_error, error_output)
                        return GitOperationResult(
                            success=False,
                            command=command_str,
                            stdout=process.stdout,
                            stderr=process.stderr,
                            returncode=process.returncode,
                            retries=retries,
                            error_type=last_error,
                            error_message=error_message
                        )

                # 非网络错误，直接返回
                return GitOperationResult(
                    success=False,
                    command=command_str,
                    stdout=process.stdout,
                    stderr=process.stderr,
                    returncode=process.returncode,
                    retries=retries,
                    error_type=NetworkError.UNKNOWN,
                    error_message=error_output
                )

            except subprocess.TimeoutExpired:
                last_error = NetworkError.TIMEOUT

                if retries < self.max_retries:
                    retries += 1
                    wait_time = self.retry_delay * retries

                    if self.logger:
                        self.logger.log(
                            "WARNING",
                            f"{operation_name} 超时，{wait_time}秒后重试",
                            f"尝试 {retries + 1}/{self.max_retries + 1}"
                        )

                    time.sleep(wait_time)
                    continue
                else:
                    error_message = f"{operation_name} 超时（{timeout}秒），已重试 {self.max_retries} 次"
                    return GitOperationResult(
                        success=False,
                        command=command_str,
                        stdout="",
                        stderr="操作超时",
                        returncode=-1,
                        retries=retries,
                        error_type=last_error,
                        error_message=error_message
                    )

            except Exception as e:
                # 其他异常
                return GitOperationResult(
                    success=False,
                    command=command_str,
                    stdout="",
                    stderr=str(e),
                    returncode=-1,
                    retries=retries,
                    error_type=NetworkError.UNKNOWN,
                    error_message=f"未知错误: {str(e)}"
                )

        # 不应该到这里
        return GitOperationResult(
            success=False,
            command=command_str,
            stdout="",
            stderr="未知错误",
            returncode=-1,
            retries=retries,
            error_type=NetworkError.UNKNOWN,
            error_message="未知错误"
        )

    def _format_error_message(self, operation: str, error_type: NetworkError, details: str) -> str:
        """
        格式化错误消息

        Args:
            operation: 操作名称
            error_type: 错误类型
            details: 错误详情

        Returns:
            格式化的错误消息
        """
        messages = {
            NetworkError.TIMEOUT: f"{operation} 超时，请检查网络连接",
            NetworkError.CONNECTION_REFUSED: f"{operation} 连接被拒绝，请检查远程仓库配置",
            NetworkError.HOST_NOT_FOUND: f"{operation} 找不到主机，请检查远程仓库 URL",
            NetworkError.PERMISSION_DENIED: f"{operation} 权限被拒绝，请检查推送权限",
            NetworkError.BRANCH_NOT_FOUND: f"{operation} 分支不存在",
            NetworkError.UNKNOWN: f"{operation} 失败: {details[:100]}"
        }

        return messages.get(error_type, f"{operation} 失败: {details[:100]}")

    def check_remote_branch(
        self,
        branch: str,
        remote: str = "origin",
        timeout: Optional[int] = None
    ) -> GitOperationResult:
        """
        检查远程分支是否存在

        Args:
            branch: 分支名
            remote: 远程名称
            timeout: 超时时间

        Returns:
            操作结果
        """
        return self.run_git_with_retry(
            ["ls-remote", "--heads", remote, branch],
            operation_name=f"检查远程分支 {remote}/{branch}",
            timeout=timeout,
            check_remote=True
        )

    def fetch_branch(
        self,
        branch: str,
        remote: str = "origin",
        timeout: Optional[int] = None
    ) -> GitOperationResult:
        """
        拉取远程分支

        Args:
            branch: 分支名
            remote: 远程名称
            timeout: 超时时间

        Returns:
            操作结果
        """
        return self.run_git_with_retry(
            ["fetch", remote, branch],
            operation_name=f"拉取远程分支 {remote}/{branch}",
            timeout=timeout,
            check_remote=True
        )

    def push_branch(
        self,
        branch: str,
        remote: str = "origin",
        timeout: Optional[int] = None,
        force: bool = False
    ) -> GitOperationResult:
        """
        推送分支到远程

        Args:
            branch: 分支名
            remote: 远程名称
            timeout: 超时时间
            force: 是否强制推送

        Returns:
            操作结果
        """
        args = ["push", remote, branch]
        if force:
            args.append("--force")

        return self.run_git_with_retry(
            args,
            operation_name=f"推送分支 {remote}/{branch}",
            timeout=timeout,
            check_remote=True
        )


def main():
    """命令行入口（用于测试）"""
    helper = GitNetworkHelper()

    print("测试 Git 网络操作:")
    print("=" * 50)

    # 测试 1: 检查远程分支
    print("\n测试 1: 检查远程分支")
    result = helper.check_remote_branch("test")
    print(f"  成功: {result.success}")
    print(f"  返回码: {result.returncode}")
    if result.error_type:
        print(f"  错误类型: {result.error_type.value}")
    if result.error_message:
        print(f"  错误消息: {result.error_message}")
    if result.retries > 0:
        print(f"  重试次数: {result.retries}")


if __name__ == "__main__":
    main()
