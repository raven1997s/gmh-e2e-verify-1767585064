#!/usr/bin/env python3
"""
Git Merge Helper - 合并执行器

功能：
- 执行完整的合并流程
- 集成日志记录、分支选择、冲突检测
- 自动处理回滚
- 并发保护（防止同时执行多个合并）

Generated: 2026-01-04
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# 导入其他模块
from logger import MergeLogger
from branch_selector import BranchSelector
from conflict_checker import ConflictChecker
from conflict_resolver import ConflictResolver
from merge_prechecker import MergePrechecker, PrecheckStatus
from git_status_checker import GitStatusChecker, StatusCode
from git_network_helper import GitNetworkHelper, NetworkError
from git_utils import GitRepository, GitRemote, FileLock


class MergeExecutor:
    """合并执行器"""

    def __init__(self, config=None):
        """
        初始化合并执行器

        Args:
            config: 配置对象（可选）

        Raises:
            RuntimeError: 初始化失败
        """
        try:
            # 加载配置
            if config is None:
                from config import MergeConfig
                config = MergeConfig.load()

            self.config = config

            # 初始化各组件，传入配置
            self.logger = MergeLogger()
            self.selector = BranchSelector()
            self.checker = ConflictChecker()
            self.resolver = ConflictResolver(config=config)
            self.prechecker = MergePrechecker(config=config)
            self.status_checker = GitStatusChecker()
            self.network_helper = GitNetworkHelper(self.logger, config)
            self.temp_branch = ""

            # 并发锁（使用跨平台的 FileLock）
            self.file_lock = None

        except Exception as e:
            raise RuntimeError(f"合并执行器初始化失败: {e}")

    def _acquire_lock(self) -> bool:
        """
        获取合并锁，防止并发执行

        使用跨平台的 FileLock 实现并发控制

        Returns:
            是否成功获取锁
        """
        try:
            # 获取日志目录（复用 logger 的逻辑）
            logs_dir = self.logger.logs_dir
        except Exception:
            # 如果 logger 未初始化，查找 Git 仓库
            try:
                logs_dir = GitRepository.get_logs_dir()
            except Exception:
                # 使用临时目录
                import tempfile
                logs_dir = Path(tempfile.gettempdir()) / ".claude" / "logs"

        lock_path = logs_dir / ".merge.lock"
        self.file_lock = FileLock(lock_path)

        # 尝试获取非阻塞锁
        return self.file_lock.acquire(blocking=False)

    def _release_lock(self):
        """释放合并锁"""
        if self.file_lock:
            try:
                self.file_lock.release()
            except Exception:
                pass  # 忽略释放锁时的错误
            finally:
                self.file_lock = None

    def run_git(self, args: list, check: bool = True) -> subprocess.CompletedProcess:
        """
        执行 Git 命令

        Args:
            args: 命令参数列表
            check: 是否检查返回码

        Returns:
            subprocess.CompletedProcess 对象
        """
        return subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            check=check
        )

    def _get_remote_name(self) -> str:
        """
        自动检测远程仓库名称

        Returns:
            远程仓库名称，默认为 'origin'
        """
        return GitRemote.get_remote_name()

    def check_environment(self) -> bool:
        """
        检查环境（增强版，支持各种 Git 状态检查）

        Returns:
            环境是否满足要求
        """
        # 检查 Git 仓库
        result = self.run_git(["rev-parse", "--is-inside-work-tree"], check=False)
        if result.returncode != 0:
            self.logger.log("ERROR", "不是 Git 仓库", "请在 Git 仓库中运行")
            return False

        # 使用 GitStatusChecker 进行详细检查
        status = self.status_checker.check_repository()

        if not status["is_clean"]:
            # 记录详细的错误信息
            for item in status["items"][:10]:  # 最多显示 10 个
                # 过滤掉 .DS_Store 和 .claude
                if ".DS_Store" not in item.file and ".claude/" not in item.file:
                    self.logger.log("ERROR", f"文件变更: {item.file}", item.description)

            # 记录特殊状态
            if status["has_submodule_changes"]:
                self.logger.log("ERROR", "Submodule 检测到变更", "请先处理 submodule 更改")

            if status["has_lfs_locked"]:
                self.logger.log("ERROR", "LFS 锁定文件", "请先解锁或提交 LFS 文件")

            if status["has_assume_unchanged"]:
                self.logger.log("ERROR", "Assume-unchanged 文件", "请先恢复或处理这些文件")

            # 生成建议
            suggestions = self.status_checker.get_clean_suggestions(status)
            suggestion_text = "\n".join(suggestions)
            self.logger.steps.append(f"\n💡 清理建议:\n{suggestion_text}")

            return False

        self.logger.log("INFO", "检查环境", "工作目录干净（已忽略 .DS_Store 和 .claude）")
        return True

    def check_commits_ahead(self, target_branch: str) -> tuple:
        """
        检查当前分支相对于目标分支的新提交

        Args:
            target_branch: 目标分支名

        Returns:
            (新提交数量, 提交列表)
        """
        count, commits = self.selector.check_commits_ahead(target_branch)

        if count == 0:
            # 没有新提交，提前拦截
            self.logger.log("WARNING", "没有需要合并的新内容",
                          f"当前分支的所有更改已经在 {target_branch} 分支中了")
            return (0, [])

        self.logger.log("INFO", f"检测到 {count} 个新提交需要合并",
                      f"最新提交: {commits[0] if commits else 'N/A'}")
        return (count, commits)

    def create_temp_branch(self, target_branch: str) -> bool:
        """
        创建临时分支

        Args:
            target_branch: 目标分支名

        Returns:
            是否创建成功
        """
        current_branch = self.logger.current_branch
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.temp_branch = f"merge-{current_branch}-to-{target_branch}-{timestamp}"

        result = self.run_git(
            ["checkout", "-b", self.temp_branch, target_branch],
            check=False
        )

        if result.returncode != 0:
            self.logger.log("ERROR", "创建临时分支失败", result.stderr)
            return False

        self.logger.log("INFO", "创建临时分支", self.temp_branch)
        self.logger.set_branches(current_branch, target_branch, self.temp_branch)
        return True

    def pull_latest_code(self, branch: str) -> bool:
        """
        拉取最新代码（使用网络重试机制）

        Args:
            branch: 分支名

        Returns:
            是否成功
        """
        remote = self._get_remote_name()
        result = self.network_helper.fetch_branch(branch, remote=remote)

        if not result.success:
            error_msg = result.error_message or "未知错误"
            self.logger.log("WARNING", f"拉取 {branch} 代码失败", error_msg)
            if result.retries > 0:
                self.logger.log("INFO", "重试信息", f"已重试 {result.retries} 次")
            return False

        self.logger.log("INFO", f"拉取 {branch} 分支最新代码",
                      result.stdout.strip() or "Already up to date")
        if result.retries > 0:
            self.logger.log("INFO", "网络重试", f"第 {result.retries + 1} 次尝试成功")
        return True

    def merge_branch(self, source_branch: str) -> bool:
        """
        合并分支

        Args:
            source_branch: 源分支名

        Returns:
            是否合并成功
        """
        result = self.run_git(
            ["merge", source_branch, "--no-edit", "--no-ff"],
            check=False
        )

        if result.returncode != 0:
            self.logger.log("ERROR", "合并失败", result.stderr)
            return False

        # 提取变更文件数量
        output = result.stdout
        if "changed," in output.lower() or "insertion" in output.lower():
            # 尝试提取文件数量
            import re
            match = re.search(r"(\d+) files? changed", output, re.IGNORECASE)
            files_msg = match.group(0) if match else "多个文件"
            self.logger.log("INFO", f"合并 {source_branch} 分支", files_msg)
        else:
            self.logger.log("INFO", f"合并 {source_branch} 分支", result.stdout.strip())

        return True

    def rollback(self) -> bool:
        """
        回滚操作

        Returns:
            是否回滚成功
        """
        self.logger.log("WARNING", "开始自动回滚", "恢复到合并前状态")

        # 中止合并
        self.run_git(["merge", "--abort"], check=False)

        # 切换回原分支
        current = self.logger.current_branch
        result = self.run_git(["checkout", current], check=False)

        if result.returncode != 0:
            self.logger.log("ERROR", "切换回原分支失败", result.stderr)
            # 提供详细的手动恢复指导
            recovery_steps = f"""
        ⚠️  自动回滚失败，仓库处于不确定状态！

        请手动执行以下步骤恢复：

        1️⃣  查看当前状态：
            git status

        2️⃣  如果有合并冲突，先中止合并：
            git merge --abort

        3️⃣  查看所有分支：
            git branch -a

        4️⃣  切换回原分支：
            git checkout {current}

        5️⃣  如果临时分支存在，删除它：
            git branch -D <临时分支名>

        6️⃣  确认状态：
            git status
            git branch --show-current
        """
            self.logger.steps.append(recovery_steps)
            return False

        # 删除临时分支
        if self.temp_branch:
            self.run_git(["branch", "-D", self.temp_branch], check=False)

        self.logger.log("INFO", "回滚完成", f"已切换回 {current}")
        return True

    def push_and_cleanup(self, target_branch: str) -> bool:
        """
        推送并清理（使用网络重试机制）

        Args:
            target_branch: 目标分支名

        Returns:
            是否成功
        """
        current = self.logger.current_branch
        remote = self._get_remote_name()

        # 推送临时分支
        if self.temp_branch:
            result = self.network_helper.push_branch(self.temp_branch, remote=remote)
            if not result.success:
                error_msg = result.error_message or "未知错误"
                self.logger.log("ERROR", "推送临时分支失败", error_msg)
                if result.retries > 0:
                    self.logger.log("INFO", "重试信息", f"已重试 {result.retries} 次")
                return False

        # 切换到目标分支
        result = self.run_git(["checkout", target_branch], check=False)
        if result.returncode != 0:
            self.logger.log("ERROR", "切换到目标分支失败", result.stderr)
            return False

        # 合并临时分支
        if self.temp_branch:
            result = self.run_git(
                ["merge", self.temp_branch, "--no-edit"],
                check=False
            )
            if result.returncode != 0:
                self.logger.log("ERROR", "合并临时分支失败", result.stderr)
                return False

        # 推送目标分支（使用网络重试）
        result = self.network_helper.push_branch(target_branch, remote=remote)
        if not result.success:
            error_msg = result.error_message or "未知错误"
            self.logger.log("ERROR", f"推送 {target_branch} 失败", error_msg)
            if result.retries > 0:
                self.logger.log("INFO", "重试信息", f"已重试 {result.retries} 次")
            return False

        self.logger.log("SUCCESS", f"推送 {target_branch} 分支",
                      f"已合并到 {target_branch}")

        # 删除临时分支
        if self.temp_branch:
            # 删除本地临时分支
            self.run_git(["branch", "-D", self.temp_branch], check=False)

            # 删除远程临时分支（使用网络重试）
            result = self.network_helper.run_git_with_retry(
                ["push", remote, "--delete", self.temp_branch],
                operation_name=f"删除远程临时分支 {self.temp_branch}",
                check_remote=True
            )
            if not result.success:
                self.logger.log("WARNING", "删除远程临时分支失败", result.error_message or "请手动删除")
            else:
                self.logger.log("INFO", "清理临时分支", self.temp_branch)

        # 切换回原分支
        result = self.run_git(["checkout", current], check=False)
        if result.returncode != 0:
            self.logger.log("WARNING", "切换回原分支失败", result.stderr)
        else:
            self.logger.log("INFO", "返回原分支", current)

        return True

    def execute(self, target_branch: Optional[str] = None,
               target_branches: Optional[list] = None) -> bool:
        """
        执行合并流程（支持单分支或批量合并）

        Args:
            target_branch: 单个目标分支名（可选，如果不指定则交互式选择）
            target_branches: 多个目标分支名列表（批量合并，优先级高于 target_branch）

        Returns:
            是否全部成功
        """
        # 获取并发锁
        if not self._acquire_lock():
            print("\n❌ 另一个合并操作正在进行，请稍后重试")
            return False

        try:
            # 执行合并（原有逻辑）
            return self._execute_internal(target_branch, target_branches)
        finally:
            # 释放锁
            self._release_lock()

    def _execute_internal(self, target_branch: Optional[str] = None,
                         target_branches: Optional[list] = None) -> bool:
        """
        内部执行逻辑

        Args:
            target_branch: 单个目标分支名
            target_branches: 多个目标分支名列表

        Returns:
            是否全部成功
        """
        # 批量合并处理
        if target_branches:
            # 检查受保护分支
            protected_found = []
            for branch in target_branches:
                if self.resolver.is_protected_branch(branch):
                    protected_found.append(branch)

            if protected_found:
                print(f"\n❌ 禁止操作受保护分支: {', '.join(protected_found)}")
                print(f"受保护分支列表: {', '.join(self.resolver.get_protected_branches())}")
                return False

            # 获取当前分支
            original_current, _ = self.selector.get_branches()

            # 🔍 预检所有分支（全部成功或全部失败）
            print(f"\n🔍 预检 {len(target_branches)} 个分支...")
            print("-" * 50)

            # 获取远程名称
            remote = self._get_remote_name()

            precheck_results = self.prechecker.precheck_all_branches(
                target_branches, original_current, remote=remote
            )

            # 显示预检结果
            for result in precheck_results:
                icon = "✅" if result.can_merge else "❌" if result.status == PrecheckStatus.ERROR else "⚠️ "
                print(f"  {icon} {result.branch}: {result.message}")

            # 检查是否可以继续
            summary = self.prechecker.get_summary()
            print("-" * 50)

            if not summary["can_proceed"]:
                print(f"\n❌ 预检失败，无法执行批量合并")
                print(f"   成功: {summary['success']}/{summary['total']}")
                print(f"   错误: {summary['errors']}/{summary['total']}")

                # 记录到日志
                self.logger = MergeLogger()
                self.logger.current_branch = original_current
                self.logger.target_branches = target_branches
                self.logger.is_batch_merge = True
                self.logger.log("INFO", "预检结果", f"成功: {summary['success']}, 错误: {summary['errors']}")
                for result in precheck_results:
                    if not result.can_merge:
                        self.logger.log("ERROR", f"{result.branch}: {result.message}", result.details or "")
                self.logger.set_result("FAILED", "预检失败")
                self.logger.save()
                self.logger.print_log_link()

                return False

            # 预检全部通过，执行批量合并
            print(f"\n✅ 预检通过，开始批量合并...")
            print(f"目标分支: {', '.join(target_branches)}")
            print("-" * 50)

            results = {}
            merge_errors = []  # 记录合并过程中的错误

            for i, branch in enumerate(target_branches, 1):
                print(f"\n[{i}/{len(target_branches)}] 合并到 {branch}...")

                # 创建新的 logger 实例用于每个分支
                self.logger = MergeLogger()

                # 执行单个分支合并
                try:
                    success = self._execute_single_merge(branch, original_current)
                    results[branch] = "SUCCESS" if success else "FAILED"
                    if not success:
                        merge_errors.append(branch)
                except Exception as e:
                    results[branch] = "FAILED"
                    merge_errors.append(branch)
                    self.logger.log("ERROR", f"合并异常: {str(e)}", "")

                # 如果是"全部成功或全部失败"模式，遇到错误就停止
                if merge_errors:
                    print(f"\n⚠️  合并到 {branch} 失败，停止批量合并")
                    break

            # 打印汇总
            print("\n" + "=" * 50)
            print("📊 批量合并结果汇总:")
            for branch in target_branches:
                result = results.get(branch, "SKIPPED")
                status_icon = "✅" if result == "SUCCESS" else "❌" if result == "FAILED" else "⏭️ "
                print(f"  {status_icon} {branch}: {result}")

            success_count = sum(1 for r in results.values() if r == "SUCCESS")
            print(f"\n成功: {success_count}/{len(target_branches)}")

            # 如果有错误，记录详细日志
            if merge_errors:
                self.logger = MergeLogger()
                self.logger.current_branch = original_current
                self.logger.target_branches = target_branches
                self.logger.is_batch_merge = True
                self.logger.log("INFO", "批量合并结果", f"成功: {success_count}/{len(target_branches)}")
                self.logger.set_result("PARTIAL", f"部分分支合并失败: {', '.join(merge_errors)}")
                self.logger.save()

            # 返回是否全部成功
            return len(merge_errors) == 0

        # 单分支合并（原有逻辑）
        return self._execute_single_merge(target_branch)

    def _execute_single_merge(self, target_branch: Optional[str],
                              original_current: Optional[str] = None) -> bool:
        """
        执行单个分支的合并流程

        Args:
            target_branch: 目标分支名
            original_current: 原始当前分支（批量合并时使用）

        Returns:
            是否成功
        """
        # 0. 获取当前分支（提前保存，避免后续切换后丢失）
        current, branches = self.selector.get_branches()

        # 批量合并时使用原始当前分支
        if original_current:
            current = original_current

        self.logger.current_branch = current  # 设置到 logger 中

        # 1. 检查环境
        if not self.check_environment():
            self.logger.set_result("FAILED", "环境检查失败")
            self.logger.save()
            return False

        # 2. 获取分支信息
        self.logger.log("INFO", "获取分支信息", f"当前: {current}, 可用: {len(branches)} 个")

        # 3. 选择目标分支
        if target_branch is None:
            target_branch = self.selector.select_branch()
            if target_branch is None:
                self.logger.log("INFO", "用户取消操作", "")
                self.logger.set_result("CANCELLED", "用户取消")
                self.logger.save()
                return False

        self.logger.target_branch = target_branch

        # 4. 检查差异
        count, commits = self.check_commits_ahead(target_branch)
        if count == 0:
            self.logger.set_result("SKIP", "无需合并")
            self.logger.save()
            return False

        # 5. 创建临时分支
        if not self.create_temp_branch(target_branch):
            self.logger.set_result("FAILED", "创建临时分支失败")
            self.logger.save()
            return False

        # 6. 拉取最新代码
        self.pull_latest_code(target_branch)

        # 7. 合并当前分支
        if not self.merge_branch(current):
            self.rollback()
            self.logger.set_result("FAILED", "合并失败")
            self.logger.save()
            return False

        # 8. 检查冲突
        has_conflicts = self.checker.check_conflicts()

        if has_conflicts:
            # 有冲突，获取冲突文件列表
            conflicts = self.checker.analyze_conflicts()
            conflict_files = [c['file'] for c in conflicts]

            # 使用 resolver 生成详细的分析和建议
            resolution_result = self.resolver.resolve_all_conflicts(conflict_files)

            # 记录冲突文件
            for conflict in conflicts:
                self.logger.log("ERROR", f"冲突文件: {conflict['file']}",
                              f"{conflict['conflict_count']} 个冲突点")

            # 添加详细的解决建议到日志
            self.logger.steps.append(f"\n{resolution_result['summary']}")

            # 添加常用命令到日志
            commands = self.resolver.get_resolution_commands(conflict_files)
            self.logger.steps.append("\n".join(commands))

            # 回滚
            self.rollback()

            self.logger.set_result("FAILED", f"检测到冲突 ({resolution_result['total_files']} 个文件, {resolution_result['total_blocks']} 个冲突块)")
            self.logger.save()

            # 打印冲突报告
            print(f"\n🔴 检测到 {len(conflict_files)} 个文件有冲突")
            print(f"📊 共 {resolution_result['total_blocks']} 个冲突块")
            print("\n" + resolution_result['summary'])
            print("\n⚠️  已自动回滚，请参考上方建议手动处理冲突")
            self.logger.print_log_link()

            return False

        # 9. 无冲突，完成合并
        self.logger.log("SUCCESS", "检测冲突", "无冲突")

        # 10. 推送并清理
        if not self.push_and_cleanup(target_branch):
            self.rollback()
            self.logger.set_result("FAILED", "推送失败")
            self.logger.save()
            return False

        # 11. 完成
        self.logger.set_result("SUCCESS")
        self.logger.save()

        print(f"\n✅ 成功合并到 {target_branch} 分支")
        self.logger.print_log_link()

        return True


def main():
    """命令行入口（用于测试）"""
    if len(sys.argv) > 1:
        target = sys.argv[1]
    else:
        target = None

    executor = MergeExecutor()
    success = executor.execute(target)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
