#!/usr/bin/env python3
"""
Git Merge Helper - 冲突检测器

功能：
- 检测合并冲突的文件
- 分析冲突类型和位置
- 提供冲突解决建议

Generated: 2026-01-04
"""

import subprocess
import sys
from typing import List, Dict, Tuple


class ConflictChecker:
    """冲突检测器"""

    def __init__(self):
        """初始化冲突检测器"""
        self.conflicted_files = []
        self.conflict_details = {}

    def check_conflicts(self) -> bool:
        """
        检查是否有冲突

        Returns:
            True 如果有冲突，False 如果没有冲突
        """
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=U"],
            capture_output=True,
            text=True,
            check=False
        )

        self.conflicted_files = [
            f for f in result.stdout.strip().split("\n")
            if f.strip()
        ]

        return len(self.conflicted_files) > 0

    def get_conflicted_files(self) -> List[str]:
        """
        获取冲突文件列表

        Returns:
            冲突文件列表
        """
        return self.conflicted_files

    def get_conflict_details(self, file_path: str) -> Dict:
        """
        获取指定文件的冲突详情

        Args:
            file_path: 文件路径

        Returns:
            冲突详情字典
        """
        result = subprocess.run(
            ["git", "diff", file_path],
            capture_output=True,
            text=True,
            check=False
        )

        content = result.stdout
        if not content:
            return {}

        # 解析冲突内容
        lines = content.split("\n")
        conflicts = []
        current_conflict = []

        in_conflict = False
        marker_count = 0

        for line in lines:
            if line.startswith("<<<<<<<") or line.startswith(">>>>>>>") or line.startswith("======="):
                marker_count += 1
                if line.startswith("<<<<<<<"):
                    in_conflict = True
                    current_conflict = [line]
                elif line.startswith("======="):
                    current_conflict.append(line)
                elif line.startswith(">>>>>>>"):
                    current_conflict.append(line)
                    in_conflict = False
                    conflicts.append("\n".join(current_conflict))
                    current_conflict = []
            elif in_conflict:
                current_conflict.append(line)

        return {
            "file": file_path,
            "conflict_count": len(conflicts),
            "conflicts": conflicts
        }

    def analyze_conflicts(self) -> List[Dict]:
        """
        分析所有冲突

        Returns:
            冲突详情列表
        """
        conflicts = []

        for file_path in self.conflicted_files:
            details = self.get_conflict_details(file_path)
            conflicts.append(details)

        return conflicts

    def format_conflict_report(self) -> str:
        """
        格式化冲突报告

        Returns:
            格式化的冲突报告字符串
        """
        if not self.has_conflicts():
            return "✓ 没有检测到冲突"

        report = ["=" * 60]
        report.append(f"❌ 检测到 {len(self.conflicted_files)} 个冲突文件：")
        report.append("")

        for i, file_path in enumerate(self.conflicted_files, 1):
            report.append(f"文件 {i}: {file_path}")

            # 获取冲突详情
            details = self.get_conflict_details(file_path)
            if details.get("conflicts"):
                report.append("")
                for j, conflict in enumerate(details["conflicts"][:3], 1):  # 只显示前3个冲突
                    lines = conflict.split("\n")
                    report.append("  " + "-" * 56)
                    for line in lines:
                        report.append(f"  {line}")
                    if j >= 2 and len(details["conflicts"]) > 3:
                        report.append(f"  ... (还有 {len(details['conflicts']) - 3} 个冲突)")
                        break

            report.append("")

        report.append("=" * 60)
        return "\n".join(report)

    def has_conflicts(self) -> bool:
        """
        是否有冲突

        Returns:
            True 如果有冲突，否则 False
        """
        return len(self.conflicted_files) > 0

    def get_conflict_summary(self) -> str:
        """
        获取冲突摘要

        Returns:
            冲突摘要字符串
        """
        if not self.has_conflicts():
            return "✓ 没有检测到冲突"

        return f"❌ 检测到 {len(self.conflicted_files)} 个冲突文件"


def main():
    """命令行入口（用于测试）"""
    checker = ConflictChecker()

    print("检查合并冲突...")
    has_conflicts = checker.check_conflicts()

    if has_conflicts:
        print("\n" + checker.format_conflict_report())
        print("\n建议:")
        print("  1. 切换到目标分支: git checkout <target>")
        print("  2. 手动合并: git merge <source>")
        print("  3. 解决冲突文件")
        print("  4. 提交: git add . && git commit -m '解决冲突'")
    else:
        print(checker.get_conflict_summary())


if __name__ == "__main__":
    main()
