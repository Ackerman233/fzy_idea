"""
convert_toolhop.py - 将 ToolHop benchmark 转换为 eval_dataset 格式

用法:
    python3 scripts/convert_toolhop.py [选项]

示例:
    # 转换前 10 题
    python3 scripts/convert_toolhop.py -n 10

    # 转换全部 995 题
    python3 scripts/convert_toolhop.py -o datasets/toolhop_full.json

    # 指定输入路径
    python3 scripts/convert_toolhop.py -i /path/to/ToolHop.json -n 20
"""

import argparse
import json
import os
import sys
from pathlib import Path

TOOLHOP_SYSTEM_PROMPTS = {
    "direct": (
        "You will be asked a question, and should provide a short answer.\n"
        "If the answer is a date, format is as follows: YYYY-MM-DD (ISO standard)\n"
        "If the answer is a name, format it as follows: Firstname Lastname\n"
        "If the answer contains any number, format it as a number, not a word, and only output that number. "
        "Do not include leading 0s.\n\n"
        "Please provide the answer in the following format: <answer>your answer here</answer>\n"
        "Answer as short as possible."
    ),
    "mandatory": (
        "You will be asked a question with some tools, and should provide a short final answer.\n"
        "Please note that you must call the tool at every step, you must not use your own knowledge. "
        "Your final answer must also be returned from the tool.\n"
        "If the final answer is a date, format is as follows: YYYY-MM-DD (ISO standard)\n"
        "If the final answer is a name, format it as follows: Firstname Lastname\n"
        "If the final answer contains any number, format it as a number, not a word, and only output that number. "
        "Do not include leading 0s.\n\n"
        "Please provide the final answer in the following format: <answer>final answer here</answer>\n"
        "Answer as short as possible."
    ),
    "free": (
        "You will be asked a question with some tools, and should provide a short final answer.\n"
        "If the final answer is a date, format is as follows: YYYY-MM-DD (ISO standard)\n"
        "If the final answer is a name, format it as follows: Firstname Lastname\n"
        "If the final answer contains any number, format it as a number, not a word, and only output that number. "
        "Do not include leading 0s.\n\n"
        "Please provide the final answer in the following format: <answer>final answer here</answer>\n"
        "Answer as short as possible."
    ),
}


def convert_sample(sample: dict, scenario: str) -> dict:
    """转换单个 ToolHop 样本为 eval_dataset test_case 格式"""
    # 提取工具列表
    tools = []
    for sub_q, tool_def in sample["tools"].items():
        # 找到对应的函数代码
        func_name = tool_def["name"]
        func_code = ""
        for func_str in sample["functions"]:
            if func_str.split("def")[1].split("(")[0].strip() == func_name:
                func_code = func_str
                break

        tools.append({
            "name": func_name,
            "description": tool_def.get("description", ""),
            "code": func_code,
            "parameters": tool_def.get("parameters", {
                "type": "object", "properties": {}, "required": []
            }),
        })

    # 子任务信息
    sub_task = sample.get("sub_task", {})

    return {
        "id": f"toolhop_{sample['id']}",
        "question": sample["question"],
        "expected_answer": sample["answer"],
        "answer_keywords": [sample["answer"]],
        "answer_type": sample.get("answer_type", "string"),
        "domain": sample.get("domain", ""),
        "sub_task": sub_task,
        "tools": tools,
        "source": "ToolHop",
        "category": sample.get("domain", "general"),
    }


def main():
    parser = argparse.ArgumentParser(
        description="将 ToolHop benchmark 转换为 eval_dataset 格式"
    )
    parser.add_argument(
        "-i", "--input",
        default="/opt/data/private/src/ToolHop/dataset/ToolHop.json",
        help="ToolHop.json 路径",
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="输出路径 (默认: datasets/toolhop_<scenario>_<n>.json)",
    )
    parser.add_argument(
        "-n", "--limit",
        type=int,
        default=None,
        help="只转换前 N 道题",
    )
    parser.add_argument(
        "--scenario",
        choices=["direct", "mandatory", "free"],
        default="free",
        help="评估场景 (默认: free)",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="数据集名称",
    )
    args = parser.parse_args()

    # 加载数据
    print(f"加载 ToolHop: {args.input}")
    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"总样本数: {len(data)}")

    # 限制数量
    if args.limit:
        data = data[:args.limit]

    # 转换
    test_cases = []
    for sample in data:
        tc = convert_sample(sample, args.scenario)
        test_cases.append(tc)

    name = args.name or f"toolhop_{args.scenario}"
    system_prompt = TOOLHOP_SYSTEM_PROMPTS[args.scenario]

    dataset = {
        "name": name,
        "description": f"ToolHop benchmark ({args.scenario} mode, {len(test_cases)} items)",
        "system_prompt": system_prompt,
        "tools": [],  # 工具在每个 test_case 内部
        "test_cases": test_cases,
    }

    # 输出
    if args.output is None:
        script_dir = Path(__file__).resolve().parent.parent
        output_path = str(script_dir / "datasets" / f"{name}_{len(test_cases)}.json")
    else:
        output_path = args.output

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)

    print(f"\n转换完成:")
    print(f"  数据集名称: {name}")
    print(f"  场景: {args.scenario}")
    print(f"  题目数: {len(test_cases)}")
    print(f"  平均工具数: {sum(len(tc['tools']) for tc in test_cases) / len(test_cases):.1f}")
    print(f"  输出文件: {output_path}")


if __name__ == "__main__":
    main()
