#!/usr/bin/env python3
"""
Git Merge Helper - 冲突解决建议器

功能：
- 分析冲突文件内容
- 提供冲突解决建议
- 生成详细的冲突报告

Generated: 2026-01-04
"""

import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING

# 避免循环导入
if TYPE_CHECKING:
    from config import MergeConfig


class ConflictResolver:
    """冲突解决建议器"""

    # 默认受保护分支列表
    DEFAULT_PROTECTED_BRANCHES = ["pre", "prod", "production", "master-prod", "pre-prod"]

    def __init__(self, project_root: Optional[Path] = None, config=None):
        """
        初始化冲突解决器

        Args:
            project_root: 项目根目录
            config: 配置对象（可选）
        """
        if project_root is None:
            project_root = Path.cwd()
        self.project_root = project_root
        self.conflict_details = []

        # 从配置获取受保护分支列表
        if config and config.protected_branches:
            self.protected_branches = config.protected_branches
        else:
            self.protected_branches = self.DEFAULT_PROTECTED_BRANCHES.copy()

        # 从配置获取最大文件大小限制
        if config:
            self.max_file_size = config.max_conflict_file_size
        else:
            self.max_file_size = 10 * 1024 * 1024  # 10MB

    def is_protected_branch(self, branch: str) -> bool:
        """
        检查是否为受保护的分支

        使用精确匹配和常见变体匹配，避免误杀合法分支如 "feature/pre-fix"

        Args:
            branch: 分支名

        Returns:
            是否为受保护分支
        """
        branch_lower = branch.lower()

        # 为每个受保护分支生成常见变体
        for protected in self.protected_branches:
            protected_lower = protected.lower()
            # 精确匹配
            if branch_lower == protected_lower:
                return True
            # 常见前缀/后缀变体
            if (branch_lower.startswith(protected_lower + "/") or
                branch_lower.startswith(protected_lower + "-") or
                branch_lower.endswith("-" + protected_lower) or
                branch_lower.endswith("_" + protected_lower) or
                branch_lower.startswith(protected_lower + "_")):
                return True

        return False

    def get_protected_branches(self) -> List[str]:
        """
        获取所有受保护的分支名称

        Returns:
            受保护分支列表
        """
        return self.protected_branches.copy()

    def analyze_conflict(self, file_path: str) -> Dict:
        """
        分析单个文件的冲突

        Args:
            file_path: 冲突文件路径

        Returns:
            冲突分析结果
        """
        full_path = self.project_root / file_path

        if not full_path.exists():
            return {
                "file": file_path,
                "status": "file_not_found",
                "suggestion": f"文件不存在: {file_path}"
            }

        # 检查文件大小
        try:
            file_size = full_path.stat().st_size
            if file_size > self.max_file_size:
                size_mb = file_size / 1024 / 1024
                max_mb = self.max_file_size / 1024 / 1024
                return {
                    "file": file_path,
                    "status": "file_too_large",
                    "conflict_blocks": 0,
                    "suggestion": f"文件过大 ({size_mb:.1f}MB > {max_mb:.0f}MB)，请手动检查冲突"
                }
        except Exception as e:
            return {
                "file": file_path,
                "status": "size_check_error",
                "suggestion": f"无法检查文件大小: {str(e)}"
            }

        try:
            content = full_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            return {
                "file": file_path,
                "status": "read_error",
                "suggestion": f"无法读取文件: {str(e)}"
            }

        # 统计冲突标记
        conflict_start = content.count("<<<<<<<")
        conflict_separator = content.count("=======")
        conflict_end = content.count(">>>>>>>")

        # 分析文件类型
        file_ext = Path(file_path).suffix.lower()
        language = self._detect_language(file_ext)

        # 生成解决建议
        suggestion = self._generate_suggestion(
            file_path, file_ext, language,
            conflict_start, conflict_separator, conflict_end
        )

        return {
            "file": file_path,
            "status": "conflict",
            "language": language,
            "conflict_blocks": conflict_start,
            "markers_valid": conflict_start == conflict_separator == conflict_end,
            "suggestion": suggestion
        }

    def _detect_language(self, file_ext: str) -> str:
        """
        根据文件扩展名检测编程语言

        Args:
            file_ext: 文件扩展名

        Returns:
            编程语言名称
        """
        ext_map = {
            ".java": "Java",
            ".py": "Python",
            ".js": "JavaScript",
            ".ts": "TypeScript",
            ".jsx": "React JSX",
            ".tsx": "React TSX",
            ".vue": "Vue",
            ".xml": "XML",
            ".yml": "YAML",
            ".yaml": "YAML",
            ".json": "JSON",
            ".md": "Markdown",
            ".sql": "SQL",
            ".sh": "Shell",
            ".bash": "Bash",
            ".properties": "Properties",
            ".txt": "Text"
        }
        return ext_map.get(file_ext, "Unknown")

    def _generate_suggestion(self, file_path: str, file_ext: str,
                            language: str, conflicts: int,
                            separators: int, ends: int) -> str:
        """
        生成冲突解决建议

        Args:
            file_path: 文件路径
            file_ext: 文件扩展名
            language: 编程语言
            conflicts: 冲突块数量
            separators: 分隔符数量
            ends: 结束标记数量

        Returns:
            解决建议文本
        """
        # 验证冲突标记完整性
        if conflicts != separators or conflicts != ends:
            return f"⚠️  冲突标记不完整！可能有 {conflicts} 个开始、{separators} 个分隔、{ends} 个结束标记。请手动检查文件完整性。"

        lines = []
        lines.append(f"📄 {file_path} ({language})")
        lines.append(f"   检测到 {conflicts} 个冲突块")
        lines.append("")

        if conflicts == 0:
            lines.append("   ✅ 未检测到实际的冲突标记")
            return "\n".join(lines)

        # 根据文件类型给出建议
        if file_ext in [".java", ".py", ".js", ".ts"]:
            lines.extend(self._code_conflict_suggestion(language))
        elif file_ext in [".xml", ".yml", ".yaml", ".json"]:
            lines.extend(self._config_conflict_suggestion(language))
        elif file_ext == ".md":
            lines.extend(self._markdown_conflict_suggestion())
        else:
            lines.extend(self._generic_conflict_suggestion())

        return "\n".join(lines)

    def _code_conflict_suggestion(self, language: str) -> List[str]:
        """代码文件冲突建议"""
        return [
            "   💡 解决建议:",
            "      1. 打开文件，搜索 <<<<<<< 找到冲突位置",
            f"      2. 检查 {language} 语法：确保合并后代码可编译",
            "      3. 对比两个版本：",
            "         - 上方：当前分支的更改（保留）",
            "         - 下方：要合并分支的更改",
            "      4. 选择正确版本或手动合并",
            "      5. 删除冲突标记：<<<<<<<, =======, >>>>>>>",
            "",
            "   ⚠️  常见问题:",
            "      - 导入语句冲突：合并导入，去重",
            "      - 方法签名冲突：确认使用哪个版本",
            "      - 逻辑冲突：需要理解业务逻辑后手动合并"
        ]

    def _config_conflict_suggestion(self, language: str) -> List[str]:
        """配置文件冲突建议"""
        return [
            "   💡 解决建议:",
            "      1. 配置文件冲突通常需要手动合并",
            "      2. 检查环境差异：可能是 dev/test/prod 配置",
            "      3. 确认配置值：保留需要的配置项",
            "      4. 删除冲突标记",
            "",
            "   ⚠️  注意:",
            "      - 不要直接复制整个文件",
            "      - 确保配置格式正确（缩进、语法）"
        ]

    def _markdown_conflict_suggestion(self) -> List[str]:
        """Markdown 文件冲突建议"""
        return [
            "   💡 解决建议:",
            "      1. Markdown 冲突通常是文档内容冲突",
            "      2. 对比两个版本的内容",
            "      3. 选择保留的内容或手动合并",
            "      4. 删除冲突标记"
        ]

    def _generic_conflict_suggestion(self) -> List[str]:
        """通用冲突建议"""
        return [
            "   💡 解决建议:",
            "      1. 查看冲突内容，理解差异",
            "      2. 选择要保留的版本",
            "      3. 删除冲突标记（<<<<<<<, =======, >>>>>>>）",
            "      4. 保存文件",
            "      5. 运行: git add <file>",
            "",
            "   🔗 参考文档:",
            "      https://git-scm.com/book/zh/v2/Git-%E5%B7%A5%E5%85%B7-%E9%AB%98%E7%BA%A7%E5%90%88%E5%B9%B6"
        ]

    def resolve_all_conflicts(self, conflict_files: List[str]) -> Dict:
        """
        分析所有冲突文件

        Args:
            conflict_files: 冲突文件列表

        Returns:
            分析结果摘要
        """
        if not conflict_files:
            return {
                "total_files": 0,
                "conflicts": [],
                "summary": "无冲突文件"
            }

        self.conflict_details = []
        total_blocks = 0

        for file_path in conflict_files:
            detail = self.analyze_conflict(file_path)
            self.conflict_details.append(detail)
            total_blocks += detail.get("conflict_blocks", 0)

        # 生成摘要
        summary_lines = [
            f"📋 冲突分析报告",
            f"=" * 50,
            f"冲突文件数: {len(conflict_files)}",
            f"冲突块总数: {total_blocks}",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            f"详细分析:"
        ]

        for detail in self.conflict_details:
            summary_lines.append("")
            summary_lines.append(detail["suggestion"])

        return {
            "total_files": len(conflict_files),
            "total_blocks": total_blocks,
            "conflicts": self.conflict_details,
            "summary": "\n".join(summary_lines)
        }

    def get_resolution_commands(self, conflict_files: List[str]) -> List[str]:
        """
        获取常用的冲突解决命令

        Args:
            conflict_files: 冲突文件列表

        Returns:
            命令列表
        """
        commands = [
            "",
            "🔧 常用冲突解决命令:",
            "",
            "# 查看冲突文件详情",
            "git diff --name-only --diff-filter=U",
            "",
            "# 查看具体冲突内容",
            "git diff HEAD",
            "",
            "# 接受当前分支的版本",
        ]

        for f in conflict_files:
            commands.append(f"git checkout --ours {f}")

        commands.extend([
            "",
            "# 接受合并分支的版本",
        ])

        for f in conflict_files:
            commands.append(f"git checkout --theirs {f}")

        commands.extend([
            "",
            "# 标记冲突已解决",
        ])

        for f in conflict_files:
            commands.append(f"git add {f}")

        commands.extend([
            "",
            "# 放弃合并（如果无法解决）",
            "git merge --abort",
        ])

        return commands


def main():
    """命令行入口（用于测试）"""
    resolver = ConflictResolver()

    # 测试受保护分支检查
    print("受保护分支检查:")
    test_branches = ["test", "pre", "prod", "feature/test", "production-env"]
    for branch in test_branches:
        protected = resolver.is_protected_branch(branch)
        print(f"  {branch}: {'❌ 禁止操作' if protected else '✅ 允许操作'}")

    print("\n" + "=" * 50)

    # 测试冲突分析（模拟数据）
    print("\n冲突分析测试:")
    test_files = [
        "src/main/java/UserService.java",
        "src/main/resources/application.yml",
        "README.md"
    ]

    result = resolver.resolve_all_conflicts(test_files)
    print(result["summary"])


if __name__ == "__main__":
    main()
