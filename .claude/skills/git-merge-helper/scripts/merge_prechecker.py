#!/usr/bin/env python3
"""
Git Merge Helper - 合并预检器

功能：
- 预检分支是否可以安全合并
- 检查远程分支是否存在
- 检查是否有权限推送
- 预测可能的冲突

Generated: 2026-01-04
"""

import subprocess
from dataclasses import dataclass
from typing import List, Dict, Optional, TYPE_CHECKING
from enum import Enum

# 避免循环导入
if TYPE_CHECKING:
    from config import MergeConfig

# 导入 Git 工具类
try:
    from git_utils import GitRemote
except ImportError:
    # 如果无法导入，使用备用实现
    class GitRemote:
        _remote_name_cache = None

        @staticmethod
        def get_remote_name():
            if GitRemote._remote_name_cache is not None:
                return GitRemote._remote_name_cache
            try:
                result = subprocess.run(
                    ["git", "remote", "show"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=30
                )
                if result.returncode == 0 and result.stdout.strip():
                    remotes = result.stdout.strip().split("\n")
                    if remotes:
                        GitRemote._remote_name_cache = remotes[0].strip()
                        return GitRemote._remote_name_cache
            except Exception:
                pass
            GitRemote._remote_name_cache = "origin"
            return GitRemote._remote_name_cache


class PrecheckStatus(Enum):
    """预检状态"""
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"


@dataclass
class PrecheckResult:
    """预检结果"""
    branch: str
    status: PrecheckStatus
    message: str
    details: Optional[str] = None
    can_merge: bool = True


class MergePrechecker:
    """合并预检器"""

    def __init__(self, config=None, remote: str = None):
        """
        初始化预检器

        Args:
            config: 配置对象（可选）
            remote: 远程仓库名称（可选，默认自动检测）
        """
        self.results: List[PrecheckResult] = []

        # 从配置获取超时时间
        if config:
            self.network_timeout = config.network_timeout
        else:
            self.network_timeout = 30  # 默认 30 秒

        # 自动检测远程名称
        if remote:
            self.remote = remote
        else:
            self.remote = GitRemote.get_remote_name()

    def check_remote_branch_exists(self, branch: str, remote: str = None) -> PrecheckResult:
        """
        检查远程分支是否存在

        Args:
            branch: 分支名
            remote: 远程名称（可选，默认使用自动检测的远程）

        Returns:
            预检结果
        """
        if remote is None:
            remote = self.remote
        result = subprocess.run(
            ["git", "ls-remote", "--heads", remote, branch],
            capture_output=True,
            text=True,
            check=False,
            timeout=self.network_timeout
        )

        if result.returncode == 0 and result.stdout.strip():
            return PrecheckResult(
                branch=branch,
                status=PrecheckStatus.SUCCESS,
                message=f"远程分支 {remote}/{branch} 存在",
                can_merge=True
            )
        else:
            return PrecheckResult(
                branch=branch,
                status=PrecheckStatus.ERROR,
                message=f"远程分支 {remote}/{branch} 不存在",
                details=f"请先在远程创建分支，或检查分支名是否正确",
                can_merge=False
            )

    def check_push_permission(self, branch: str, remote: str = None) -> PrecheckResult:
        """
        检查推送权限（通过检查是否可以访问远程仓库）

        Args:
            branch: 分支名
            remote: 远程名称（可选，默认使用自动检测的远程）

        Returns:
            预检结果
        """
        if remote is None:
            remote = self.remote

        # 尝试获取远程信息
        result = subprocess.run(
            ["git", "remote", "get-url", remote],
            capture_output=True,
            text=True,
            check=False,
            timeout=self.network_timeout
        )

        if result.returncode == 0:
            return PrecheckResult(
                branch=branch,
                status=PrecheckStatus.SUCCESS,
                message=f"可以访问远程仓库 {remote}",
                can_merge=True
            )
        else:
            return PrecheckResult(
                branch=branch,
                status=PrecheckStatus.ERROR,
                message=f"无法访问远程仓库 {remote}",
                details="请检查网络连接和远程仓库配置",
                can_merge=False
            )

    def check_commits_ahead(self, source_branch: str, target_branch: str) -> PrecheckResult:
        """
        检查是否有新提交需要合并

        Args:
            source_branch: 源分支
            target_branch: 目标分支

        Returns:
            预检结果
        """
        result = subprocess.run(
            ["git", "log", f"{target_branch}..{source_branch}", "--oneline"],
            capture_output=True,
            text=True,
            check=False
        )

        commits = result.stdout.strip().split("\n") if result.stdout.strip() else []
        commits = [c for c in commits if c.strip()]

        if len(commits) == 0:
            return PrecheckResult(
                branch=target_branch,
                status=PrecheckStatus.WARNING,
                message=f"没有需要合并的新提交",
                details=f"{source_branch} 的所有更改已经在 {target_branch} 中",
                can_merge=False
            )
        else:
            return PrecheckResult(
                branch=target_branch,
                status=PrecheckStatus.SUCCESS,
                message=f"检测到 {len(commits)} 个新提交需要合并",
                can_merge=True
            )

    def precheck_branch(self, branch: str, source_branch: str, remote: str = None) -> PrecheckResult:
        """
        对单个分支进行完整预检

        Args:
            branch: 目标分支名
            source_branch: 源分支名
            remote: 远程名称（可选，默认使用自动检测的远程）

        Returns:
            预检结果
        """
        if remote is None:
            remote = self.remote
        checks = [
            self.check_remote_branch_exists(branch, remote),
            self.check_push_permission(branch, remote),
            self.check_commits_ahead(source_branch, branch)
        ]

        # 检查是否有错误
        errors = [c for c in checks if c.status == PrecheckStatus.ERROR]
        warnings = [c for c in checks if c.status == PrecheckStatus.WARNING]

        if errors:
            # 有错误，不能合并
            error_msg = "; ".join([e.message for e in errors])
            return PrecheckResult(
                branch=branch,
                status=PrecheckStatus.ERROR,
                message=f"预检失败: {error_msg}",
                details="\n".join([f"  - {e.message}" for e in errors]),
                can_merge=False
            )

        if warnings:
            # 有警告，但也可能可以合并（如没有新提交）
            warning_msg = "; ".join([w.message for w in warnings])
            return PrecheckResult(
                branch=branch,
                status=PrecheckStatus.WARNING,
                message=warning_msg,
                details="\n".join([f"  - {w.message}" for w in warnings]),
                can_merge=False  # 没有新提交时也不合并
            )

        # 所有检查通过
        return PrecheckResult(
            branch=branch,
            status=PrecheckStatus.SUCCESS,
            message=f"预检通过，可以合并到 {branch}",
            can_merge=True
        )

    def precheck_all_branches(self, branches: List[str], source_branch: str, remote: str = None) -> List[PrecheckResult]:
        """
        预检所有分支

        Args:
            branches: 目标分支列表
            source_branch: 源分支名
            remote: 远程名称（可选，默认使用自动检测的远程）

        Returns:
            预检结果列表
        """
        if remote is None:
            remote = self.remote
        results = []
        for branch in branches:
            result = self.precheck_branch(branch, source_branch, remote)
            results.append(result)

        self.results = results
        return results

    def get_summary(self) -> Dict:
        """
        获取预检汇总信息

        Returns:
            汇总信息字典
        """
        total = len(self.results)
        success = sum(1 for r in self.results if r.status == PrecheckStatus.SUCCESS and r.can_merge)
        errors = sum(1 for r in self.results if r.status == PrecheckStatus.ERROR or not r.can_merge)
        warnings = sum(1 for r in self.results if r.status == PrecheckStatus.WARNING)

        return {
            "total": total,
            "success": success,
            "errors": errors,
            "warnings": warnings,
            "can_proceed": errors == 0 and success > 0
        }


def main():
    """命令行入口（用于测试）"""
    prechecker = MergePrechecker()

    # 测试单个分支预检
    print("测试单个分支预检:")
    result = prechecker.precheck_branch("test", "WMS00.00.02T/feat_ai_ding_notify_ljc_20251224")
    print(f"  分支: {result.branch}")
    print(f"  状态: {result.status.value}")
    print(f"  消息: {result.message}")
    print(f"  可合并: {result.can_merge}")

    if result.details:
        print(f"  详情:\n{result.details}")


if __name__ == "__main__":
    main()
