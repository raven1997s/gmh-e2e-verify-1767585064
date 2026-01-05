#!/usr/bin/env python3
"""
Git Merge Helper - 配置管理

功能：
- 集中管理所有配置项
- 支持从配置文件加载
- 提供默认值

Generated: 2026-01-04
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
import json

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


@dataclass
class MergeConfig:
    """合并配置类"""

    # ==================== 网络配置 ====================
    max_retries: int = 3
    """最大重试次数"""

    retry_delay: int = 2
    """基础重试延迟（秒），后续重试会递增"""

    network_timeout: int = 30
    """网络操作超时时间（秒）"""

    # ==================== 日志清理配置 ====================
    max_week_logs: int = 10
    """一周内最多保留的日志数量"""

    max_month_logs: int = 5
    """一个月内最多保留的日志数量"""

    week_days: int = 7
    """一周的天数"""

    month_days: int = 30
    """一个月的天数"""

    # ==================== 受保护分支 ====================
    protected_branches: List[str] = field(default_factory=list)
    """受保护的分支列表，禁止合并操作"""

    # ==================== 其他配置 ====================
    max_conflict_file_size: int = 10 * 1024 * 1024
    """冲突文件最大大小（10MB），超过则提示手动处理"""

    def __post_init__(self):
        """初始化后处理，设置默认值"""
        if not self.protected_branches:
            self.protected_branches = ["pre", "prod", "production", "master-prod", "pre-prod"]

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> 'MergeConfig':
        """
        加载配置文件

        Args:
            config_path: 配置文件路径，如果不指定则自动查找

        Returns:
            配置对象
        """
        # 如果未指定配置文件路径，自动查找
        if config_path is None:
            config_path = cls._find_config_file()

        # 如果找到配置文件，加载它
        if config_path and config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return cls(**data)
            except (json.JSONDecodeError, TypeError) as e:
                print(f"⚠️  配置文件格式错误: {e}")
                print(f"   使用默认配置")
                return cls()
            except Exception as e:
                print(f"⚠️  加载配置文件失败: {e}")
                print(f"   使用默认配置")
                return cls()

        # 未找到配置文件，使用默认配置
        return cls()

    @classmethod
    def _find_config_file(cls) -> Optional[Path]:
        """
        查找配置文件

        从当前目录开始向上查找，直到找到配置文件或到达根目录
        限制遍历深度防止无限循环

        Returns:
            配置文件路径或 None
        """
        # 尝试找到 Git 仓库根目录
        repo_root = GitRepository.find_root_safe()
        if repo_root is None:
            # 未找到 Git 仓库，不遍历
            return None

        # 在 Git 仓库中查找配置文件
        config_file = repo_root / ".claude" / "skills" / "git-merge-helper" / "config.json"
        if config_file.exists():
            return config_file

        return None

    def save(self, config_path: Optional[Path] = None):
        """
        保存配置到文件

        Args:
            config_path: 配置文件路径
        """
        if config_path is None:
            # 保存到默认位置
            cwd = Path.cwd()
            config_dir = cwd / ".claude" / "skills" / "git-merge-helper"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_path = config_dir / "config.json"

        # 转换为可序列化的格式
        data = {
            'max_retries': self.max_retries,
            'retry_delay': self.retry_delay,
            'network_timeout': self.network_timeout,
            'max_week_logs': self.max_week_logs,
            'max_month_logs': self.max_month_logs,
            'week_days': self.week_days,
            'month_days': self.month_days,
            'protected_branches': self.protected_branches,
            'max_conflict_file_size': self.max_conflict_file_size,
        }

        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_summary(self) -> str:
        """
        获取配置摘要

        Returns:
            配置摘要文本
        """
        return f"""
📋 Git Merge Helper 配置
{'=' * 50}

🌐 网络配置:
  • 最大重试次数: {self.max_retries}
  • 基础重试延迟: {self.retry_delay} 秒
  • 网络超时时间: {self.network_timeout} 秒

📝 日志清理策略:
  • 一周内最多保留: {self.max_week_logs} 个日志
  • 一个月内最多保留: {self.max_month_logs} 个日志
  • 超过 {self.month_days} 天的日志将被删除

🔒 受保护分支:
  • {' | '.join(self.protected_branches)}

📄 其他:
  • 冲突文件最大大小: {self.max_conflict_file_size / 1024 / 1024:.0f} MB
"""


def main():
    """命令行入口（用于测试）"""
    # 加载配置
    config = MergeConfig.load()

    # 显示配置摘要
    print(config.get_summary())

    # 测试保存配置
    print("\n是否要保存示例配置文件? (y/n): ", end="")
    import sys
    if sys.stdin.readline().strip().lower() == 'y':
        config.save()
        print("✅ 配置文件已保存")


if __name__ == "__main__":
    main()
