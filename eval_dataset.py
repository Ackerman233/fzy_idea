"""
eval_dataset.py - 从 JSON 数据集文件加载测试用例，批量评估 LLM 工具调用效果
复用 eval_demo 的核心逻辑，支持外部数据集和动态工具加载
"""

import argparse
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable

from dotenv import load_dotenv
from openai import OpenAI
from rich.console import Console
from rich.table import Table


# ============================================================================
# 1. 数据结构
# ============================================================================

@dataclass
class TrajectoryStep:
    """记录一次工具调用的轨迹"""
    tool_name: str
    arguments: dict[str, Any]
    result: str


@dataclass
class LLMResult:
    """LLM 交互的完整结果"""
    final_answer: str
    test_case_id: str = ""
    tool_chain: list[TrajectoryStep] = field(default_factory=list)
    error: str | None = None


@dataclass
class TestCase:
    """单个测试用例"""
    id: str
    question: str
    expected_answer: str
    answer_keywords: list[str]
    source: str = ""
    category: str = ""
    answer_type: str = ""  # ToolHop: number/date/string/letter/datetime/character
    per_case_tools: list[dict[str, Any]] = field(default_factory=list)  # 每题独立工具


@dataclass
class DatasetInfo:
    """数据集信息"""
    name: str
    description: str
    system_prompt: str
    tools_schema: list[dict[str, Any]]
    tool_dispatch: dict[str, Callable[[str], str]]
    test_cases: list[TestCase]


# ============================================================================
# 2. 动态工具加载
# ============================================================================

def build_tools_from_json(tools_json: list[dict[str, Any]]) -> tuple[
    list[dict[str, Any]], dict[str, Callable[[str], str]]
]:
    """
    从 JSON 工具定义中动态构建 OpenAI tools_schema 和本地 tool_dispatch。
    JSON 中每个工具包含 code (Python 函数代码) 和 parameters (OpenAI schema)。
    """
    tools_schema: list[dict[str, Any]] = []
    tool_dispatch: dict[str, Callable[[str], str]] = {}

    for tool_def in tools_json:
        name = tool_def["name"]
        description = tool_def["description"]
        code = tool_def["code"]
        parameters = tool_def.get("parameters", {
            "type": "object",
            "properties": {},
            "required": [],
        })

        # 构建 OpenAI tools schema
        tools_schema.append({
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            },
        })

        # 动态执行代码，提取函数
        local_ns: dict[str, Any] = {}
        try:
            exec(code, {}, local_ns)  # noqa: S102
            func = local_ns.get(name)
            if func and callable(func):
                tool_dispatch[name] = func
            else:
                console = Console()
                console.print(f"[yellow]警告: 工具 '{name}' 代码中未找到同名函数[/yellow]")
        except Exception as e:
            console = Console()
            console.print(f"[yellow]警告: 工具 '{name}' 代码执行失败: {e}[/yellow]")

    return tools_schema, tool_dispatch


# ============================================================================
# 3. 数据集加载
# ============================================================================

def load_dataset(file_path: str) -> DatasetInfo:
    """从 JSON 文件加载数据集"""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    tools_schema, tool_dispatch = build_tools_from_json(data.get("tools", []))

    test_cases = []
    has_per_case_tools = False
    for tc in data.get("test_cases", []):
        per_case = tc.get("tools", [])
        if per_case:
            has_per_case_tools = True
        test_cases.append(TestCase(
            id=tc["id"],
            question=tc["question"],
            expected_answer=tc["expected_answer"],
            answer_keywords=tc.get("answer_keywords", []),
            source=tc.get("source", ""),
            category=tc.get("category", ""),
            answer_type=tc.get("answer_type", ""),
            per_case_tools=per_case,
        ))

    if has_per_case_tools:
        Console().print("[cyan]检测到 per-sample tools 模式（如 ToolHop）[/cyan]")

    return DatasetInfo(
        name=data.get("name", "unknown"),
        description=data.get("description", ""),
        system_prompt=data.get("system_prompt", "你是一个有用的助手。"),
        tools_schema=tools_schema,
        tool_dispatch=tool_dispatch,
        test_cases=test_cases,
    )


# ============================================================================
# 4. LLM 交互 (复用 eval_demo 逻辑)
# ============================================================================

def run_llm_with_tools(
    client: OpenAI,
    system_prompt: str,
    user_query: str,
    tools_schema: list[dict[str, Any]],
    tool_dispatch: dict[str, Callable[[str], str]],
    model: str = "gpt-4o-mini",
    max_rounds: int = 5,
) -> LLMResult:
    """与 LLM 交互，处理工具调用循环，直到获得最终文本回答。"""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_query},
    ]
    tool_chain: list[TrajectoryStep] = []

    for _ in range(max_rounds):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools_schema,
            tool_choice="auto",
        )
        msg = response.choices[0].message

        # 没有工具调用，说明模型给出了最终回答
        if not msg.tool_calls:
            return LLMResult(final_answer=msg.content or "", tool_chain=tool_chain)

        # 有工具调用，逐个执行
        messages.append(msg.model_dump())  # type: ignore[arg-type]

        for tc in msg.tool_calls:
            func_name = tc.function.name
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}

            # 执行本地工具
            if func_name in tool_dispatch:
                try:
                    raw_result = tool_dispatch[func_name](**args) if args else tool_dispatch[func_name]()
                except TypeError:
                    # 回退：单参数模式（兼容旧工具）
                    arg_value = next(iter(args.values()), "") if args else ""
                    raw_result = tool_dispatch[func_name](arg_value)
                # 确保结果是字符串
                result = raw_result if isinstance(raw_result, str) else json.dumps(raw_result, ensure_ascii=False, default=str)
            else:
                result = json.dumps({"error": f"未知工具: {func_name}"}, ensure_ascii=False)

            tool_chain.append(TrajectoryStep(
                tool_name=func_name,
                arguments=args,
                result=result,
            ))

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    return LLMResult(
        final_answer="[达到最大交互轮次，未获得最终回答]",
        tool_chain=tool_chain,
        error="超过最大工具调用轮次",
    )


# ============================================================================
# 5. 通用打分器
# ============================================================================

def calculate_reward(
    tool_chain: list[TrajectoryStep],
    final_answer: str,
    answer_keywords: list[str],
    tool_dispatch: dict[str, Callable[[str], str]],
) -> dict[str, Any]:
    """
    通用打分器，满分 100。
    - 关键词匹配 (60分): 最终回答是否包含 answer_keywords
    - 工具调用合理性 (30分): 是否调用了可用工具、参数是否合理
    - 冗余惩罚 (-10分): 调用不存在的工具或重复调用
    """
    breakdown: dict[str, Any] = {
        "关键词匹配": {"score": 0, "max": 60, "detail": ""},
        "工具调用合理性": {"score": 0, "max": 30, "detail": ""},
        "冗余惩罚": {"score": 0, "max": -10, "detail": ""},
    }
    total = 0

    # --- 关键词匹配 (60分) ---
    if answer_keywords:
        answer_lower = final_answer.lower() if final_answer else ""
        matched = []
        for kw in answer_keywords:
            if kw.lower() in answer_lower:
                matched.append(kw)

        if matched:
            # 匹配到的关键词越多，得分越高
            kw_score = int(60 * len(matched) / len(answer_keywords))
            breakdown["关键词匹配"]["score"] = kw_score
            breakdown["关键词匹配"]["detail"] = (
                f"匹配 {len(matched)}/{len(answer_keywords)} 个关键词: {matched}"
            )
        else:
            breakdown["关键词匹配"]["detail"] = (
                f"未匹配任何关键词 (期望: {answer_keywords})"
            )
    else:
        # 没有关键词时，检查回答是否非空
        if final_answer and final_answer.strip():
            breakdown["关键词匹配"]["score"] = 60
            breakdown["关键词匹配"]["detail"] = "回答非空（无关键词要求）"
        else:
            breakdown["关键词匹配"]["detail"] = "回答为空"
    total += breakdown["关键词匹配"]["score"]

    # --- 工具调用合理性 (30分) ---
    tool_score = 0
    tool_details = []

    if tool_chain:
        # 有工具调用
        valid_tools = set(tool_dispatch.keys())
        called_tools = {step.tool_name for step in tool_chain}

        # 调用了可用工具 (+15)
        used_valid = called_tools & valid_tools
        if used_valid:
            tool_score += 15
            tool_details.append(f"调用了可用工具: {used_valid}")

        # 工具调用有结果 (+15)
        successful_calls = [
            s for s in tool_chain
            if s.result and "error" not in s.result.lower()
        ]
        if successful_calls:
            tool_score += 15
            tool_details.append(f"成功调用 {len(successful_calls)} 次")
    else:
        # 没有工具调用，但可能不需要工具（如选择题）
        if answer_keywords and any(
            len(kw) == 1 and kw.isalpha() for kw in answer_keywords
        ):
            # 选择题不需要工具，给满分
            tool_score = 30
            tool_details.append("选择题无需工具调用")
        else:
            tool_details.append("未调用任何工具")

    breakdown["工具调用合理性"]["score"] = tool_score
    breakdown["工具调用合理性"]["detail"] = "; ".join(tool_details)
    total += tool_score

    # --- 冗余惩罚 (-10分) ---
    penalty = 0
    penalty_details = []

    valid_tools = set(tool_dispatch.keys())
    for step in tool_chain:
        if step.tool_name not in valid_tools:
            penalty -= 5
            penalty_details.append(f"调用了不存在的工具: {step.tool_name}")

    tool_counts = Counter(s.tool_name for s in tool_chain)
    for tool_name, count in tool_counts.items():
        if count > 2:
            penalty -= 5
            penalty_details.append(f"工具 {tool_name} 调用次数过多: {count} 次")

    breakdown["冗余惩罚"]["score"] = penalty
    breakdown["冗余惩罚"]["detail"] = "; ".join(penalty_details) if penalty_details else "无冗余调用"
    total += penalty

    total = max(0, min(100, total))

    return {"total": total, "breakdown": breakdown}


def toolhop_exact_match(
    ground_truth: str,
    solution_str: str,
    tool_chain: list[TrajectoryStep],
) -> dict[str, Any]:
    """
    ToolHop 精确匹配打分（来自 evaluation_closed.py）。
    返回 {"correct": 0|1, "detail": str}
    """
    correct = 0
    detail = ""

    # 提取 <answer>...</answer> 标签
    extracted = solution_str
    if "<answer>" in solution_str:
        extracted = solution_str.split("<answer>")[-1]
        if "</answer>" in extracted:
            extracted = extracted.split("</answer>")[0]

    # 尝试 eval() 比较
    try:
        gt_val = eval(ground_truth.strip())  # noqa: S307
    except Exception:
        # eval 失败，用字符串匹配
        gt_clean = str(ground_truth).removesuffix(".0").lower()
        sol_clean = str(extracted).removesuffix(".0").replace(",", "").lower()
        if gt_clean in sol_clean:
            correct = 1
            detail = f"字符串匹配: '{gt_clean}' in '{sol_clean[:50]}'"
        else:
            detail = f"不匹配: 期望 '{gt_clean}', 实际 '{sol_clean[:50]}'"
    else:
        try:
            sol_val = eval(extracted.strip())  # noqa: S307
        except Exception:
            detail = f"eval 失败: '{extracted[:50]}'"
        else:
            if gt_val == sol_val:
                correct = 1
                detail = f"精确匹配: {gt_val} == {sol_val}"
            else:
                detail = f"不匹配: {gt_val} != {sol_val}"

    # 额外奖励：工具输出中包含答案
    if correct == 0 and tool_chain:
        last_tool_result = tool_chain[-1].result
        gt_clean = str(ground_truth).removesuffix(".0").lower()
        result_clean = last_tool_result.removesuffix(".0").replace(",", "").lower()
        if gt_clean in result_clean:
            correct = 1
            detail = f"工具输出包含答案: '{gt_clean}' in tool result"

    return {"correct": correct, "detail": detail}


# ============================================================================
# 6. 报告输出
# ============================================================================

def print_report(
    dataset_name: str,
    results: list[tuple[TestCase, LLMResult, dict[str, Any]]],
) -> None:
    """使用 rich 打印评估报告"""
    console = Console()

    is_toolhop = any(tc.answer_type for tc, _, _ in results)

    # 主表格
    table = Table(
        title=f"数据集评估报告: {dataset_name}",
        show_lines=True,
        expand=True,
    )
    table.add_column("ID", style="cyan", width=20)
    table.add_column("类别", width=10)
    table.add_column("工具调用", justify="center", width=8)

    if is_toolhop:
        table.add_column("结果", justify="center", width=6)
        table.add_column("匹配详情", width=50)
    else:
        table.add_column("关键词匹配\n(满分60)", justify="center", width=10)
        table.add_column("工具合理性\n(满分30)", justify="center", width=10)
        table.add_column("冗余惩罚", justify="center", width=8)
    table.add_column("最终回答 (截断)", width=40)

    correct_count = 0

    for tc, llm_result, reward in results:
        bd = reward["breakdown"]
        answer_display = (llm_result.final_answer or "[无回答]")[:80]
        if len(llm_result.final_answer or "") > 80:
            answer_display += "..."

        if is_toolhop:
            is_correct = reward.get("toolhop_correct", 0)
            correct_count += is_correct
            result_style = "green" if is_correct else "red"
            result_label = f"[{result_style}]{'✓' if is_correct else '✗'}[/{result_style}]"
            detail = bd.get("精确匹配", {}).get("detail", "")
            table.add_row(
                tc.id,
                tc.category,
                str(len(llm_result.tool_chain)),
                result_label,
                detail,
                answer_display,
            )
        else:
            total_score = reward["total"]
            score_style = "green" if total_score >= 80 else "yellow" if total_score >= 50 else "red"
            table.add_row(
                tc.id,
                tc.category,
                str(len(llm_result.tool_chain)),
                f"{bd['关键词匹配']['score']}/{bd['关键词匹配']['max']}",
                f"{bd['工具调用合理性']['score']}/{bd['工具调用合理性']['max']}",
                str(bd["冗余惩罚"]["score"]),
                f"[{score_style}]{total_score}[/{score_style}]",
                answer_display,
            )

    console.print(table)

    # 汇总统计
    if is_toolhop:
        total_count = len(results)
        accuracy = 100 * correct_count / total_count if total_count else 0
        console.print(f"\n[bold]汇总 (ToolHop 模式):[/bold]")
        console.print(f"  总题数: {total_count}")
        console.print(f"  正确数: {correct_count}")
        console.print(f"  准确率: {accuracy:.1f}%")
    else:
        total_scores = [r["total"] for _, _, r in results]
        if total_scores:
            avg_score = sum(total_scores) / len(total_scores)
            pass_count = sum(1 for s in total_scores if s >= 60)
            console.print(f"\n[bold]汇总:[/bold]")
            console.print(f"  总题数: {len(total_scores)}")
            console.print(f"  平均分: {avg_score:.1f}/100")
            console.print(f"  及格率 (>=60分): {pass_count}/{len(total_scores)} ({100*pass_count/len(total_scores):.0f}%)")

    # 详细得分
    console.print("\n" + "=" * 80)
    console.print("[bold]详细打分明细[/bold]")
    console.print("=" * 80)

    for tc, llm_result, reward in results:
        console.print(f"\n[bold cyan]▸ {tc.id}[/bold cyan] ({tc.category})")
        console.print(f"  题目: {tc.question[:80]}...")
        console.print(f"  期望答案: {tc.expected_answer}")
        console.print(f"  实际回答: {(llm_result.final_answer or '[无回答]')[:100]}")

        bd = reward["breakdown"]
        for item_name, item_data in bd.items():
            console.print(f"  {item_name}: {item_data['score']}/{item_data['max']} — {item_data['detail']}")
        if is_toolhop:
            status = "✓ 正确" if reward.get("toolhop_correct") else "✗ 错误"
            console.print(f"  [bold]结果: {status}[/bold]")
        else:
            console.print(f"  [bold]总分: {reward['total']}/100[/bold]")

        if llm_result.tool_chain:
            console.print("  工具调用链:")
            for i, step in enumerate(llm_result.tool_chain, 1):
                console.print(f"    {i}. {step.tool_name}({step.arguments})")
        if llm_result.error:
            console.print(f"  [red]错误: {llm_result.error}[/red]")


# ============================================================================
# 7. Main
# ============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="从 JSON 数据集文件加载测试用例，批量评估 LLM 工具调用效果"
    )
    parser.add_argument(
        "--dataset", "-d",
        required=True,
        help="JSON 数据集文件路径",
    )
    parser.add_argument(
        "--model", "-m",
        default=None,
        help="模型名称 (默认从 .env 读取)",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=5,
        help="最大工具调用轮次 (默认 5)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="只评估前 N 个测试用例",
    )
    args = parser.parse_args()

    console = Console()
    console.print("[bold]eval_dataset - 批量数据集评估[/bold]\n")

    # 加载环境变量
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model_name = args.model or os.getenv("MODEL_NAME", "gpt-4o-mini")

    if not api_key:
        console.print("[red]错误: 请在 .env 文件中设置 OPENAI_API_KEY[/red]")
        sys.exit(1)

    # 加载数据集
    console.print(f"加载数据集: {args.dataset}")
    dataset = load_dataset(args.dataset)
    console.print(f"数据集名称: {dataset.name}")
    console.print(f"数据集描述: {dataset.description}")
    console.print(f"测试用例数: {len(dataset.test_cases)}")
    console.print(f"可用工具数: {len(dataset.tools_schema)}")
    console.print(f"工具列表: {[t['function']['name'] for t in dataset.tools_schema]}")

    if args.limit:
        dataset.test_cases = dataset.test_cases[:args.limit]
        console.print(f"限制评估前 {args.limit} 个用例")

    # 初始化客户端
    client_kwargs: dict[str, str] = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = OpenAI(**client_kwargs)

    console.print(f"\nAPI Base URL: {base_url or '默认 (OpenAI)'}")
    console.print(f"模型: {model_name}")
    console.print(f"最大轮次: {args.max_rounds}\n")

    # 逐题评估
    results: list[tuple[TestCase, LLMResult, dict[str, Any]]] = []
    use_toolhop_mode = any(tc.answer_type for tc in dataset.test_cases)

    for i, tc in enumerate(dataset.test_cases, 1):
        console.print(f"[yellow][{i}/{len(dataset.test_cases)}] 正在测试: {tc.id}...[/yellow]")

        # 确定本题使用的工具（per-case 优先，否则用全局）
        if tc.per_case_tools:
            tc_schema, tc_dispatch = build_tools_from_json(tc.per_case_tools)
        else:
            tc_schema = dataset.tools_schema
            tc_dispatch = dataset.tool_dispatch

        llm_result = run_llm_with_tools(
            client=client,
            system_prompt=dataset.system_prompt,
            user_query=tc.question,
            tools_schema=tc_schema,
            tool_dispatch=tc_dispatch,
            model=model_name,
            max_rounds=args.max_rounds,
        )
        llm_result.test_case_id = tc.id

        # 打分：ToolHop 模式用精确匹配，否则用关键词匹配
        if use_toolhop_mode and tc.answer_type:
            match_result = toolhop_exact_match(
                ground_truth=tc.expected_answer,
                solution_str=llm_result.final_answer,
                tool_chain=llm_result.tool_chain,
            )
            reward = {
                "total": 100 if match_result["correct"] else 0,
                "breakdown": {
                    "精确匹配": {
                        "score": 100 if match_result["correct"] else 0,
                        "max": 100,
                        "detail": match_result["detail"],
                    },
                },
                "toolhop_correct": match_result["correct"],
            }
        else:
            reward = calculate_reward(
                tool_chain=llm_result.tool_chain,
                final_answer=llm_result.final_answer,
                answer_keywords=tc.answer_keywords,
                tool_dispatch=tc_dispatch,
            )

        results.append((tc, llm_result, reward))
        score_label = f"{'✓' if reward.get('toolhop_correct') else '✗'}" if use_toolhop_mode else f"{reward['total']}/100"
        console.print(f"  → 完成，{score_label}\n")

    # 打印报告
    print_report(dataset.name, results)


if __name__ == "__main__":
    main()
