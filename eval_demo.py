"""
Black-Box Prompt Optimization - Tool Use Evaluation Demo
测试不同 System Prompt 在指导 LLM 调用工具时的表现，并对执行轨迹打分
"""

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from dotenv import load_dotenv
from openai import OpenAI
from rich.console import Console
from rich.table import Table

# ============================================================================
# 1. 定义 Mock 工具 (Tools)
# ============================================================================

# 模拟天气数据
MOCK_WEATHER_DATA: dict[str, dict[str, Any]] = {
    "北京": {"city": "北京", "temperature": 28, "unit": "°C", "condition": "晴"},
    "上海": {"city": "上海", "temperature": 32, "unit": "°C", "condition": "多云"},
    "广州": {"city": "广州", "temperature": 35, "unit": "°C", "condition": "雷阵雨"},
    "深圳": {"city": "深圳", "temperature": 33, "unit": "°C", "condition": "阴"},
}


def get_weather(city: str) -> str:
    """查询指定城市的天气信息"""
    data = MOCK_WEATHER_DATA.get(city)
    if data:
        return json.dumps(data, ensure_ascii=False)
    return json.dumps({"error": f"未找到城市 '{city}' 的天气数据"}, ensure_ascii=False)


def calculate_math(expression: str) -> str:
    """安全地计算数学表达式"""
    # 只允许数字、运算符、括号和小数点
    sanitized = re.sub(r"[^0-9+\-*/().%\s]", "", expression)
    if not sanitized.strip():
        return json.dumps({"error": "无效的数学表达式"}, ensure_ascii=False)
    try:
        result = eval(sanitized)  # noqa: S307 - 仅用于本地 demo，已做输入清理
        return json.dumps({"expression": expression, "result": result}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"计算失败: {str(e)}"}, ensure_ascii=False)


# OpenAI Tools Schema 定义
TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询指定城市的当前天气信息，包括温度和天气状况",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称，例如：北京、上海、广州、深圳",
                    }
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_math",
            "description": "计算数学表达式，支持加减乘除等基本运算",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "数学表达式字符串，例如：'28 * 5'、'100 / 3'",
                    }
                },
                "required": ["expression"],
            },
        },
    },
]

# 本地工具函数映射
TOOL_DISPATCH: dict[str, Callable[[str], str]] = {
    "get_weather": get_weather,
    "calculate_math": calculate_math,
}


# ============================================================================
# 2. 准备测试数据 (Inputs)
# ============================================================================

USER_QUERY: str = "帮我查一下北京今天的天气，然后告诉我如果气温乘以 5 是多少？"

EXPECTED_ANSWER: str = "北京今天28°C，晴。28乘以5等于140。"

# 3 个不同风格的 System Prompt
PROMPTS: list[dict[str, str]] = [
    {
        "name": "极简风格",
        "prompt": "你是一个有用的助手。根据用户的问题，使用提供的工具来获取信息并回答。",
    },
    {
        "name": "CoT 思考风格",
        "prompt": (
            "你是一个严谨的助手。在回答用户问题时，请按以下步骤思考：\n"
            "1. 仔细分析用户的需求，识别需要调用哪些工具\n"
            "2. 按逻辑顺序调用工具，注意工具之间的依赖关系\n"
            "3. 获取工具结果后，进行必要的计算和推理\n"
            "4. 最后给出完整、准确的回答\n\n"
            "请确保每一步都有明确的推理过程。"
        ),
    },
    {
        "name": "JSON 规划风格",
        "prompt": (
            "你是一个结构化的任务执行助手。对于每个用户请求，你必须严格按照以下流程执行：\n\n"
            "【规划阶段】先在内部生成一个 JSON 格式的执行计划：\n"
            '{"plan": [{"step": 1, "action": "tool_name", "args": {...}, "depends_on": null}]}\n\n'
            "【执行阶段】按照计划依次调用工具。\n\n"
            "【汇总阶段】将所有工具结果整合，给出最终回答。\n\n"
            "注意：工具调用之间的依赖关系必须正确，例如需要先获取天气数据才能进行计算。"
        ),
    },
]


# ============================================================================
# 3. LLM 交互模块 (LLM Runner)
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
    prompt_name: str = ""
    tool_chain: list[TrajectoryStep] = field(default_factory=list)
    error: str | None = None


def run_llm_with_tools(
    client: OpenAI,
    system_prompt: str,
    user_query: str,
    model: str = "gpt-4o-mini",
    max_rounds: int = 5,
) -> LLMResult:
    """
    与 LLM 交互，处理工具调用循环，直到获得最终文本回答。
    max_rounds 防止死循环。
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_query},
    ]
    tool_chain: list[TrajectoryStep] = []

    for round_idx in range(max_rounds):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS_SCHEMA,
            tool_choice="auto",
        )
        msg = response.choices[0].message

        # 没有工具调用，说明模型给出了最终回答
        if not msg.tool_calls:
            return LLMResult(
                final_answer=msg.content or "",
                tool_chain=tool_chain,
            )

        # 有工具调用，逐个执行
        messages.append(msg.model_dump())  # type: ignore[arg-type]

        for tc in msg.tool_calls:
            func_name = tc.function.name
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}

            # 执行本地工具
            if func_name in TOOL_DISPATCH:
                # 工具函数接收第一个参数值
                arg_value = next(iter(args.values()), "") if args else ""
                result = TOOL_DISPATCH[func_name](arg_value)
            else:
                result = json.dumps({"error": f"未知工具: {func_name}"}, ensure_ascii=False)

            tool_chain.append(TrajectoryStep(
                tool_name=func_name,
                arguments=args,
                result=result,
            ))

            # 将工具结果加入对话
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    # 超过最大轮次
    return LLMResult(
        final_answer="[达到最大交互轮次，未获得最终回答]",
        tool_chain=tool_chain,
        error="超过最大工具调用轮次",
    )


# ============================================================================
# 4. 核心：轨迹打分器 (Trajectory Scorer)
# ============================================================================

# 定义正确的工具调用期望
EXPECTED_TOOLS = {"get_weather", "calculate_math"}
CORRECT_CITY = "北京"


def calculate_reward(
    tool_chain: list[TrajectoryStep],
    final_answer: str,
    expected_answer: str,
) -> dict[str, Any]:
    """
    对工具调用轨迹和最终回答进行打分，满分 100。
    返回包含各项得分明细和总分的字典。
    """
    breakdown: dict[str, Any] = {
        "工具选择": {"score": 0, "max": 40, "detail": ""},
        "参数正确性": {"score": 0, "max": 30, "detail": ""},
        "结果正确性": {"score": 0, "max": 30, "detail": ""},
        "冗余惩罚": {"score": 0, "max": -10, "detail": ""},
    }
    total = 0

    called_tools = {step.tool_name for step in tool_chain}

    # --- 工具选择 (+40分) ---
    # 检查是否调用了 get_weather 和 calculate_math
    tool_score = 0
    if "get_weather" in called_tools:
        tool_score += 20
    if "calculate_math" in called_tools:
        tool_score += 20
    breakdown["工具选择"]["score"] = tool_score
    missing = EXPECTED_TOOLS - called_tools
    if missing:
        breakdown["工具选择"]["detail"] = f"缺少工具调用: {missing}"
    else:
        breakdown["工具选择"]["detail"] = "正确调用了 get_weather 和 calculate_math"
    total += tool_score

    # --- 参数正确性 (+30分) ---
    param_score = 0
    param_details = []
    for step in tool_chain:
        if step.tool_name == "get_weather":
            city = step.arguments.get("city", "")
            if city == CORRECT_CITY:
                param_score += 15
                param_details.append(f"get_weather 城市正确: {city}")
            else:
                param_details.append(f"get_weather 城市错误: 期望 {CORRECT_CITY}, 实际 {city}")
        elif step.tool_name == "calculate_math":
            expr = step.arguments.get("expression", "")
            # 检查表达式是否包含关键数字 28 和 5（或运算结果 140）
            if "28" in expr and "5" in expr:
                param_score += 15
                param_details.append(f"calculate_math 表达式合理: {expr}")
            elif "140" in expr:
                param_score += 10  # 直接写结果也算部分正确
                param_details.append(f"calculate_math 表达式包含结果: {expr}")
            else:
                param_details.append(f"calculate_math 表达式可能不正确: {expr}")

    breakdown["参数正确性"]["score"] = param_score
    breakdown["参数正确性"]["detail"] = "; ".join(param_details) if param_details else "未调用相关工具"
    total += param_score

    # --- 结果正确性 (+30分) ---
    result_score = 0
    result_details = []
    answer_lower = final_answer.lower() if final_answer else ""

    # 检查是否包含北京天气信息 (28°C)
    if "28" in answer_lower and ("北京" in answer_lower or "beijing" in answer_lower):
        result_score += 15
        result_details.append("包含正确的北京天气温度 (28°C)")
    else:
        result_details.append("未正确包含北京天气温度")

    # 检查是否包含计算结果 (140)
    if "140" in answer_lower:
        result_score += 15
        result_details.append("包含正确的计算结果 (140)")
    else:
        result_details.append("未包含正确的计算结果")

    breakdown["结果正确性"]["score"] = result_score
    breakdown["结果正确性"]["detail"] = "; ".join(result_details)
    total += result_score

    # --- 冗余惩罚 (-10分) ---
    penalty = 0
    penalty_details = []
    # 检查是否调用了不存在的工具
    valid_tools = set(TOOL_DISPATCH.keys())
    for step in tool_chain:
        if step.tool_name not in valid_tools:
            penalty -= 5
            penalty_details.append(f"调用了不存在的工具: {step.tool_name}")
    # 检查是否有重复调用（同一工具调用超过 2 次视为冗余）
    from collections import Counter
    tool_counts = Counter(s.tool_name for s in tool_chain)
    for tool, count in tool_counts.items():
        if count > 2:
            penalty -= 5
            penalty_details.append(f"工具 {tool} 调用次数过多: {count} 次")

    breakdown["冗余惩罚"]["score"] = penalty
    breakdown["冗余惩罚"]["detail"] = "; ".join(penalty_details) if penalty_details else "无冗余调用"
    total += penalty  # penalty 为负数或零

    # 总分限制在 0-100
    total = max(0, min(100, total))

    return {"total": total, "breakdown": breakdown}


# ============================================================================
# 5. 输出对比报告
# ============================================================================


def print_report(results: list[tuple[str, LLMResult, dict[str, Any]]]) -> None:
    """使用 rich 打印对比报告表格"""
    console = Console()

    # 主表格
    table = Table(
        title="System Prompt 工具调用效果对比报告",
        show_lines=True,
        expand=True,
    )
    table.add_column("Prompt 名称", style="cyan", width=16)
    table.add_column("工具调用次数", justify="center", width=10)
    table.add_column("工具选择\n(满分40)", justify="center", width=10)
    table.add_column("参数正确性\n(满分30)", justify="center", width=10)
    table.add_column("结果正确性\n(满分30)", justify="center", width=10)
    table.add_column("冗余惩罚\n(最多-10)", justify="center", width=10)
    table.add_column("总分", justify="center", style="bold", width=8)
    table.add_column("最终回答 (截断)", width=50)

    for prompt_name, llm_result, reward in results:
        bd = reward["breakdown"]
        # 截断最终回答用于展示
        answer_display = (llm_result.final_answer or "[无回答]")[:120]
        if len(llm_result.final_answer or "") > 120:
            answer_display += "..."

        total_score = reward["total"]
        score_style = "green" if total_score >= 80 else "yellow" if total_score >= 50 else "red"

        table.add_row(
            prompt_name,
            str(len(llm_result.tool_chain)),
            f"{bd['工具选择']['score']}/{bd['工具选择']['max']}",
            f"{bd['参数正确性']['score']}/{bd['参数正确性']['max']}",
            f"{bd['结果正确性']['score']}/{bd['结果正确性']['max']}",
            str(bd["冗余惩罚"]["score"]),
            f"[{score_style}]{total_score}[/{score_style}]",
            answer_display,
        )

    console.print(table)

    # 打印每个 Prompt 的详细得分
    console.print("\n" + "=" * 80)
    console.print("[bold]详细打分明细[/bold]")
    console.print("=" * 80)

    for prompt_name, llm_result, reward in results:
        console.print(f"\n[bold cyan]▸ {prompt_name}[/bold cyan]")
        bd = reward["breakdown"]
        for item_name, item_data in bd.items():
            console.print(f"  {item_name}: {item_data['score']}/{item_data['max']} — {item_data['detail']}")
        console.print(f"  [bold]总分: {reward['total']}/100[/bold]")

        if llm_result.tool_chain:
            console.print("  工具调用链:")
            for i, step in enumerate(llm_result.tool_chain, 1):
                console.print(f"    {i}. {step.tool_name}({step.arguments})")
        if llm_result.error:
            console.print(f"  [red]错误: {llm_result.error}[/red]")


# ============================================================================
# Main
# ============================================================================


def main() -> None:
    console = Console()
    console.print("[bold]Black-Box Prompt Optimization - Tool Use Evaluation[/bold]\n")

    # 加载环境变量
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model_name = os.getenv("MODEL_NAME", "gpt-4o-mini")

    if not api_key:
        console.print("[red]错误: 请在 .env 文件中设置 OPENAI_API_KEY[/red]")
        return

    client_kwargs: dict[str, str] = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url

    client = OpenAI(**client_kwargs)
    console.print(f"API Base URL: {base_url or '默认 (OpenAI)'}")
    console.print(f"模型: {model_name}")
    console.print(f"用户问题: {USER_QUERY}")
    console.print(f"期望结果: {EXPECTED_ANSWER}")
    console.print(f"测试 Prompt 数量: {len(PROMPTS)}\n")

    results: list[tuple[str, LLMResult, dict[str, Any]]] = []

    for prompt_info in PROMPTS:
        name = prompt_info["name"]
        prompt = prompt_info["prompt"]
        console.print(f"[yellow]正在测试: {name}...[/yellow]")

        # 运行 LLM
        llm_result = run_llm_with_tools(
            client=client,
            system_prompt=prompt,
            user_query=USER_QUERY,
            model=model_name,
        )
        llm_result.prompt_name = name

        # 打分
        reward = calculate_reward(
            tool_chain=llm_result.tool_chain,
            final_answer=llm_result.final_answer,
            expected_answer=EXPECTED_ANSWER,
        )

        results.append((name, llm_result, reward))
        console.print(f"  → 完成，总分: {reward['total']}/100\n")

    # 打印对比报告
    print_report(results)


if __name__ == "__main__":
    main()
