#!/usr/bin/env python3
"""
Git Merge Helper - 分支选择器

功能：
- 获取所有可用的远程分支
- 支持交互式选择目标分支
- 支持非交互式模式（参数传递）
- 支持通过数字或分支名选择

Generated: 2026-01-04
"""

import subprocess
import sys
from typing import List, Optional, Tuple

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
                    check=False
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


class BranchSelector:
    """分支选择器"""

    def __init__(self, non_interactive: bool = False):
        """
        初始化分支选择器

        Args:
            non_interactive: 是否为非交互式模式
        """
        self.non_interactive = non_interactive
        self.current_branch = ""
        self.remote_branches = []
        self.remote_name = GitRemote.get_remote_name()
        self._load_branches()

    def _load_branches(self):
        """加载分支信息"""
        # 获取当前分支
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=False
        )
        self.current_branch = result.stdout.strip()

        # 获取所有远程分支
        result = subprocess.run(
            ["git", "branch", "-r"],
            capture_output=True,
            text=True,
            check=False
        )
        branches = result.stdout.strip().split("\n")

        # 过滤掉 HEAD，只保留分支名
        # 使用自动检测的远程名称移除前缀
        remote_prefix = f"{self.remote_name}/"
        self.remote_branches = [
            b.replace(remote_prefix, "").strip()
            for b in branches
            if b.strip() and "HEAD" not in b
        ]

    def get_branches(self) -> Tuple[str, List[str]]:
        """
        获取分支信息

        Returns:
            (当前分支, 远程分支列表)
        """
        return self.current_branch, self.remote_branches

    def display_branches(self) -> Optional[int]:
        """
        显示分支列表供用户选择（交互式模式）

        Returns:
            选中的分支索引（1-based），如果用户取消则返回 None
        """
        # 非交互式模式直接返回 None
        if self.non_interactive:
            return None

        print("\n请选择目标分支：")
        print("=" * 50)

        for i, branch in enumerate(self.remote_branches, 1):
            # 标记当前分支
            marker = " ← 当前分支" if branch == self.current_branch else ""
            print(f"  {i:2d}. {branch}{marker}")

        print("=" * 50)

        while True:
            try:
                user_input = input("\n请输入数字或分支名 (q 取消): ").strip()

                # 取消
                if user_input.lower() == "q":
                    print("已取消合并操作")
                    return None

                # 数字输入
                if user_input.isdigit():
                    index = int(user_input)
                    if 1 <= index <= len(self.remote_branches):
                        selected = self.remote_branches[index - 1]
                        print(f"✓ 已选择: {selected}")
                        return index

                    print(f"❌ 无效的数字，请输入 1-{len(self.remote_branches)}")
                    continue

                # 分支名输入
                if user_input in self.remote_branches:
                    index = self.remote_branches.index(user_input) + 1
                    print(f"✓ 已选择: {user_input}")
                    return index

                print(f"❌ 未找到分支 '{user_input}'")

            except KeyboardInterrupt:
                print("\n\n已取消合并操作")
                return None
            except Exception as e:
                print(f"❌ 输入错误: {e}")

    def select_branch(self, preferred_branch: Optional[str] = None) -> Optional[str]:
        """
        选择目标分支（支持交互式和非交互式模式）

        Args:
            preferred_branch: 偏好的分支名（如果存在，直接返回）

        Returns:
            选中的分支名，如果用户取消则返回 None
        """
        # 如果有偏好分支，直接返回
        if preferred_branch:
            if preferred_branch in self.remote_branches:
                if not self.non_interactive:
                    print(f"✓ 自动选择目标分支: {preferred_branch}")
                return preferred_branch
            else:
                if self.non_interactive:
                    # 非交互式模式下分支不存在
                    print(f"❌ 分支 '{preferred_branch}' 不存在")
                    return None
                else:
                    print(f"⚠️  偏好分支 '{preferred_branch}' 不存在，请手动选择")

        # 非交互式模式：没有指定分支，返回 None
        if self.non_interactive:
            return None

        # 交互式选择
        index = self.display_branches()
        if index is None:
            return None

        return self.remote_branches[index - 1]

    def check_commits_ahead(self, target_branch: str) -> Tuple[int, List[str]]:
        """
        检查当前分支相对于目标分支的新提交数量

        Args:
            target_branch: 目标分支名

        Returns:
            (新提交数量, 提交列表)
        """
        result = subprocess.run(
            ["git", "log", f"{target_branch}..HEAD", "--oneline"],
            capture_output=True,
            text=True,
            check=False
        )

        commits = result.stdout.strip().split("\n") if result.stdout.strip() else []

        # 移除空行
        commits = [c for c in commits if c.strip()]

        return len(commits), commits


def main():
    """命令行入口（用于测试）"""
    selector = BranchSelector()
    current, branches = selector.get_branches()

    print(f"当前分支: {current}")
    print(f"可用分支: {len(branches)} 个")

    # 检查是否有新提交
    if branches:
        count, commits = selector.check_commits_ahead(branches[0])
        print(f"\n相对于 {branches[0]} 的新提交: {count} 个")
        for commit in commits[:5]:
            print(f"  - {commit}")

    # 选择分支
    selected = selector.select_branch()
    if selected:
        print(f"\n最终选择: {selected}")


if __name__ == "__main__":
    main()
