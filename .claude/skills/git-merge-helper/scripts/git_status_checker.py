#!/usr/bin/env python3
"""
Git Merge Helper - Git 状态检查器

功能：
- 检查 Git 仓库状态
- 识别特殊文件状态（submodule、LFS、assume-unchanged）
- 提供详细的错误信息和解决建议

Generated: 2026-01-04
"""

import os
import subprocess
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum


class StatusCode(Enum):
    """状态码"""
    CLEAN = "clean"
    DIRTY = "dirty"
    SUBMODULE_CHANGES = "submodule_changes"
    LFS_LOCKED = "lfs_locked"
    ASSUME_UNCHANGED = "assume_unchanged"
    ERROR = "error"


@dataclass
class StatusItem:
    """状态项"""
    file: str
    status_code: str
    status_type: StatusCode
    description: str


class GitStatusChecker:
    """Git 状态检查器"""

    # 状态代码映射
    STATUS_MAP = {
        "M": StatusCode.DIRTY,           # 已修改
        "A": StatusCode.DIRTY,           # 已添加
        "D": StatusCode.DIRTY,           # 已删除
        "R": StatusCode.DIRTY,           # 已重命名
        "C": StatusCode.DIRTY,           # 已复制
        "U": StatusCode.DIRTY,           # 已更新但未合并
        "??": StatusCode.DIRTY,         # 未跟踪
        "!!": StatusCode.DIRTY,         # 已忽略
    }

    def __init__(self, project_root: Optional[str] = None):
        """
        初始化状态检查器

        Args:
            project_root: 项目根目录
        """
        self.project_root = project_root or os.getcwd()

    def check_repository(self) -> dict:
        """
        检查 Git 仓库状态

        Returns:
            状态字典
        """
        result = {
            "is_clean": True,
            "has_changes": False,
            "has_staged": False,
            "has_unstaged": False,
            "has_untracked": False,
            "has_submodule_changes": False,
            "has_lfs_locked": False,
            "has_assume_unchanged": False,
            "items": [],
            "errors": [],
            "warnings": []
        }

        # 检查基本状态
        git_status = self._run_git(["status", "--porcelain"])
        if not git_status["success"]:
            result["errors"].append("无法获取 Git 状态")
            result["is_clean"] = False
            return result

        # 解析状态输出
        lines = git_status["stdout"].strip().split("\n") if git_status["stdout"] else []
        for line in lines:
            if not line.strip():
                continue

            # 解析状态代码
            status_code = line[:2]
            file_path = line[3:]
            status_type = self.STATUS_MAP.get(status_code[0], StatusCode.DIRTY)

            item = StatusItem(
                file=file_path,
                status_code=status_code,
                status_type=status_type,
                description=self._get_status_description(status_code)
            )
            result["items"].append(item)

            # 更新标志
            if status_code[0] != "!" and status_code[0] != "?":
                result["has_staged"] = True
                result["has_changes"] = True
            if status_code[1] != " " and status_code[1] != "!":
                result["has_unstaged"] = True
            if status_code[0] == "?" or status_code[0] == "!":
                result["has_untracked"] = True

        # 检查特殊状态
        result["has_submodule_changes"] = self._check_submodule_changes()
        result["has_lfs_locked"] = self._check_lfs_locked()
        result["has_assume_unchanged"] = self._check_assume_unchanged()

        # 判断是否干净
        # 忽略 .DS_Store 和 .claude 目录
        filtered_items = [
            item for item in result["items"]
            if ".DS_Store" not in item.file and ".claude/" not in item.file
        ]

        result["is_clean"] = (
            len(filtered_items) == 0
            and not result["has_submodule_changes"]
            and not result["has_lfs_locked"]
            and not result["has_assume_unchanged"]
        )
        result["has_changes"] = not result["is_clean"]

        return result

    def _check_submodule_changes(self) -> bool:
        """检查是否有 submodule 变更"""
        result = self._run_git(["submodule", "status"])
        if not result["success"]:
            return False

        # 检查是否有变更
        for line in result["stdout"].split("\n"):
            if any(word in line for word in ["+", "-", "U", "M"]):
                return True
        return False

    def _check_lfs_locked(self) -> bool:
        """检查是否有 LFS 锁定文件"""
        result = self._run_git(["lfs", "status"], check=False)
        if not result["success"]:
            return False

        # 检查是否有锁定文件
        for line in result["stdout"].split("\n"):
            if "locked" in line.lower():
                return True
        return False

    def _check_assume_unchanged(self) -> bool:
        """检查是否有 assume-unchanged 文件"""
        result = self._run_git(["ls-files", "-v"])
        if not result["success"]:
            return False

        # git ls-files -v 输出格式：
        # 小写 h = assume-unchanged (被标记为假设未变更)
        # 大写 H = 正常文件
        for line in result["stdout"].split("\n"):
            if line.startswith("h "):  # 只检测小写 h
                return True
        return False

    def _get_status_description(self, status_code: str) -> str:
        """
        获取状态描述

        Args:
            status_code: Git 状态代码

        Returns:
            状态描述
        """
        descriptions = {
            "M": "已修改",
            "A": "已添加到暂存区",
            "D": "已删除",
            "R": "已重命名",
            "C": "已复制",
            "U": "已更新但未合并",
            "??": "未跟踪",
            "!!": "已忽略"
        }

        staged = status_code[0]
        unstaged = status_code[1] if len(status_code) > 1 else " "

        desc = []
        if staged in descriptions:
            desc.append(f"暂存: {descriptions[staged]}")
        if unstaged in descriptions:
            desc.append(f"工作区: {descriptions[unstaged]}")

        return " | ".join(desc) if desc else "未知状态"

    def _run_git(self, args: list, check: bool = True) -> dict:
        """
        运行 Git 命令

        Args:
            args: 命令参数
            check: 是否检查返回码

        Returns:
            结果字典
        """
        try:
            process = subprocess.run(
                ["git"] + args,
                capture_output=True,
                text=True,
                check=check,
                cwd=self.project_root
            )
            return {
                "success": process.returncode == 0,
                "stdout": process.stdout,
                "stderr": process.stderr,
                "returncode": process.returncode
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "returncode": -1
            }

    def get_clean_suggestions(self, status: dict) -> List[str]:
        """
        获取清理建议

        Args:
            status: 状态字典

        Returns:
            建议列表
        """
        suggestions = []

        if status["has_staged"] or status["has_unstaged"]:
            suggestions.append("常规文件变更：")
            suggestions.append("  1. 提交更改: git commit -m '保存工作'")
            suggestions.append("  2. 或暂存更改: git stash")
            suggestions.append("")

        if status["has_submodule_changes"]:
            suggestions.append("Submodule 变更：")
            suggestions.append("  1. 更新 submodule: git submodule update")
            suggestions.append("  2. 提交 submodule: 在 submodule 目录中提交")
            suggestions.append("")

        if status["has_lfs_locked"]:
            suggestions.append("LFS 锁定文件：")
            suggestions.append("  1. 查看锁定: git lfs locks")
            suggestions.append("  2. 解锁文件: git lfs unlock <file>")
            suggestions.append("")

        if status["has_assume_unchanged"]:
            suggestions.append("Assume-unchanged 文件：")
            suggestions.append("  1. 查看文件: git ls-files -v")
            suggestions.append("  2. 恢复文件: git update-index --no-assume-unchanged <file>")
            suggestions.append("")

        return suggestions


def main():
    """命令行入口（用于测试）"""
    checker = GitStatusChecker()

    print("检查 Git 仓库状态:")
    print("=" * 50)

    status = checker.check_repository()

    if status["is_clean"]:
        print("✅ 工作目录干净")
    else:
        print("❌ 工作目录不干净")
        print(f"\n有变更的文件数: {len(status['items'])}")

        for item in status["items"][:10]:
            print(f"  {item.status_code} {item.file}")

        if len(status["items"]) > 10:
            print(f"  ... 还有 {len(status['items']) - 10} 个文件")

        print("\n清理建议:")
        suggestions = checker.get_clean_suggestions(status)
        for suggestion in suggestions:
            print(suggestion)


if __name__ == "__main__":
    main()
