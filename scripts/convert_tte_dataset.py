"""
convert_tte_dataset.py - 将 Test-Time-Tool-Evol 的原始 JSON 数据集转换为 eval_dataset 格式

用法:
    python3 scripts/convert_tte_dataset.py <输入文件> [选项]

示例:
    # 转换单个文件
    python3 scripts/convert_tte_dataset.py /path/to/scibench/cal_calculus.json

    # 指定输出路径和题目数量
    python3 scripts/convert_tte_dataset.py /path/to/scibench/cal_calculus.json -o datasets/my_set.json -n 20

    # 转换整个目录
    python3 scripts/convert_tte_dataset.py /path/to/scibench/ -o datasets/scibench_all.json

    # 附加工具（从 tool_helpers 导入）
    python3 scripts/convert_tte_dataset.py /path/to/scibench/cal_calculus.json --tools chemistry
"""

import argparse
import json
import os
import sys
from pathlib import Path

# 工具模板：根据 --tools 参数选择要附加工具的类别
TOOL_TEMPLATES = {
    "chemistry": [
        {
            "name": "count_atoms",
            "description": "计算分子式中各类原子的数量，返回字典",
            "code": "def count_atoms(molecular_formula):\n    import re, json\n    pattern = r'([A-Z][a-z]*)([0-9]*)'\n    matches = re.findall(pattern, molecular_formula)\n    atom_counts = {}\n    for element, count in matches:\n        if element:\n            atom_counts[element] = int(count) if count else 1\n    return json.dumps({'result': atom_counts})",
            "parameters": {
                "type": "object",
                "properties": {
                    "molecular_formula": {"type": "string", "description": "分子式，例如 C6H12O6"}
                },
                "required": ["molecular_formula"]
            }
        },
        {
            "name": "count_hydrogen_atoms",
            "description": "计算分子式中氢原子的数量",
            "code": "def count_hydrogen_atoms(molecular_formula):\n    import json\n    if 'H' not in molecular_formula:\n        return json.dumps({'result': 0})\n    h_index = molecular_formula.find('H')\n    num_str = ''\n    for i in range(h_index + 1, len(molecular_formula)):\n        if molecular_formula[i].isdigit():\n            num_str += molecular_formula[i]\n        else:\n            break\n    count = int(num_str) if num_str else 1\n    return json.dumps({'result': count})",
            "parameters": {
                "type": "object",
                "properties": {
                    "molecular_formula": {"type": "string", "description": "分子式，例如 C10H21NO4"}
                },
                "required": ["molecular_formula"]
            }
        },
        {
            "name": "count_oxygen_atoms",
            "description": "计算分子式中氧原子的数量",
            "code": "def count_oxygen_atoms(molecular_formula):\n    import json\n    if 'O' not in molecular_formula:\n        return json.dumps({'result': 0})\n    o_index = molecular_formula.find('O')\n    num_str = ''\n    for i in range(o_index + 1, len(molecular_formula)):\n        if molecular_formula[i].isdigit():\n            num_str += molecular_formula[i]\n        else:\n            break\n    count = int(num_str) if num_str else 1\n    return json.dumps({'result': count})",
            "parameters": {
                "type": "object",
                "properties": {
                    "molecular_formula": {"type": "string", "description": "分子式，例如 H2O"}
                },
                "required": ["molecular_formula"]
            }
        },
        {
            "name": "calculate_molecule_mass",
            "description": "将摩尔质量(kg/mol)转换为单个分子的质量(kg)",
            "code": "def calculate_molecule_mass(molar_mass):\n    import json\n    avogadro_number = 6.02214076e23\n    molecule_mass = molar_mass / avogadro_number\n    return json.dumps({'result': f'{molecule_mass:.3e} kg'})",
            "parameters": {
                "type": "object",
                "properties": {
                    "molar_mass": {"type": "number", "description": "摩尔质量 (kg/mol)"}
                },
                "required": ["molar_mass"]
            }
        },
    ],
    "physics": [
        {
            "name": "calculate_thrust_force",
            "description": "计算火箭推力：推力 = 燃料燃烧率 × 排气速度",
            "code": "def calculate_thrust_force(fuel_burn_rate, exhaust_velocity):\n    import json\n    thrust_force = fuel_burn_rate * exhaust_velocity\n    return json.dumps({'result': f'{thrust_force:.6e} N'})",
            "parameters": {
                "type": "object",
                "properties": {
                    "fuel_burn_rate": {"type": "number", "description": "燃料燃烧率 (kg/s)"},
                    "exhaust_velocity": {"type": "number", "description": "排气速度 (m/s)"}
                },
                "required": ["fuel_burn_rate", "exhaust_velocity"]
            }
        },
        {
            "name": "calculate_net_force",
            "description": "计算净力：推力 - 重力",
            "code": "def calculate_net_force(thrust_force, gravitational_force):\n    import json\n    net_force = thrust_force - gravitational_force\n    return json.dumps({'result': f'{net_force:.6e} N'})",
            "parameters": {
                "type": "object",
                "properties": {
                    "thrust_force": {"type": "number", "description": "推力 (N)"},
                    "gravitational_force": {"type": "number", "description": "重力 (N)"}
                },
                "required": ["thrust_force", "gravitational_force"]
            }
        },
        {
            "name": "calculate_delta_v",
            "description": "齐奥尔科夫斯基火箭方程计算速度变化 Δv = ve * ln(m0/mf)",
            "code": "def calculate_delta_v(exhaust_velocity, initial_mass, fuel_mass):\n    import math, json\n    final_mass = initial_mass - fuel_mass\n    delta_v = exhaust_velocity * math.log(initial_mass / final_mass)\n    return json.dumps({'result': f'{delta_v:.6e} m/s'})",
            "parameters": {
                "type": "object",
                "properties": {
                    "exhaust_velocity": {"type": "number", "description": "排气速度 (m/s)"},
                    "initial_mass": {"type": "number", "description": "初始总质量 (kg)"},
                    "fuel_mass": {"type": "number", "description": "燃料质量 (kg)"}
                },
                "required": ["exhaust_velocity", "initial_mass", "fuel_mass"]
            }
        },
    ],
    "math": [
        {
            "name": "calculate_math",
            "description": "计算数学表达式，支持加减乘除等基本运算",
            "code": "def calculate_math(expression):\n    import re, json\n    sanitized = re.sub(r'[^0-9+\\-*/().%\\s]', '', expression)\n    if not sanitized.strip():\n        return json.dumps({'error': '无效的数学表达式'})\n    try:\n        result = eval(sanitized)\n        return json.dumps({'expression': expression, 'result': result})\n    except Exception as e:\n        return json.dumps({'error': f'计算失败: {str(e)}'})",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "数学表达式，例如 '28 * 5'"}
                },
                "required": ["expression"]
            }
        },
    ],
}

# 默认系统提示词
DEFAULT_SYSTEM_PROMPTS = {
    "scibench": "你是一个严谨的科学计算助手。在回答用户问题时，请按以下步骤思考：\n1. 仔细分析题目，识别需要计算的物理量或化学量\n2. 如果有可用的工具，优先调用工具来辅助计算\n3. 获取工具结果后，进行必要的推理和计算\n4. 最后给出完整、准确的数值答案\n\n请确保每一步都有明确的推理过程，最终答案用纯数字表示。",
    "scieval": "你是一个科学知识问答助手。请仔细阅读题目和选项，选择最准确的答案。你的回答应该只包含选项字母（A、B、C 或 D），格式为：答案是 X。",
    "scievo": "你是一个严谨的科学计算助手。在回答用户问题时，请按以下步骤思考：\n1. 仔细分析题目，识别需要计算的物理量或化学量\n2. 如果有可用的工具，优先调用工具来辅助计算\n3. 获取工具结果后，进行必要的推理和计算\n4. 最后给出完整、准确的数值答案\n\n请确保每一步都有明确的推理过程，最终答案用纯数字表示。",
}


def load_tte_json(file_path: str) -> list[dict]:
    """加载 TTE 原始 JSON 文件"""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        # 可能是 adapt_tools 格式（key-value 字典），转为列表
        return list(data.values())
    return data


def load_tte_directory(dir_path: str) -> list[dict]:
    """加载整个目录下的所有 JSON 文件"""
    all_items = []
    for fname in sorted(os.listdir(dir_path)):
        if fname.endswith(".json") and not fname.startswith("."):
            fpath = os.path.join(dir_path, fname)
            items = load_tte_json(fpath)
            all_items.extend(items)
    return all_items


def detect_dataset_type(items: list[dict]) -> str:
    """根据数据特征推断数据集类型"""
    if not items:
        return "unknown"
    first = items[0]
    if "type" in first and first["type"] in ("multiple-choice", "filling"):
        return "scieval"
    if "solution" in first:
        return "scibench"
    if "source" in first:
        # 区分 scibench 和 scievo：scievo 来源更杂
        return "scibench"
    return "scibench"


def is_multiple_choice(item: dict) -> bool:
    """判断是否为选择题"""
    return item.get("type") == "multiple-choice"


def extract_answer(item: dict, _dataset_type: str) -> tuple[str, list[str]]:
    """
    从原始数据中提取答案和关键词。
    返回 (expected_answer, answer_keywords)
    """
    raw_answer = item.get("answer", "")

    if isinstance(raw_answer, list):
        # scieval 选择题: ["D"] → "D"
        answer = raw_answer[0] if raw_answer else ""
        keywords = [answer]
    else:
        answer = str(raw_answer).strip()
        # 去掉开头的空格和正号
        answer = answer.lstrip(" +")
        keywords = [answer]

    return answer, keywords


def convert_item(item: dict, index: int, dataset_type: str) -> dict | None:
    """转换单个数据项为 test_case 格式"""
    question = item.get("question", "").strip()
    if not question:
        return None

    answer, keywords = extract_answer(item, dataset_type)
    if not answer:
        return None

    source = item.get("source", "")
    category = item.get("category", "")

    # 生成 ID
    problem_id = item.get("problemid", "").strip()
    if problem_id:
        case_id = f"{source}_{problem_id}".replace(" ", "_")
    else:
        case_id = f"{dataset_type}_{index}"

    return {
        "id": case_id,
        "question": question,
        "expected_answer": answer,
        "answer_keywords": keywords,
        "source": source,
        "category": category,
    }


def detect_tools_needed(items: list[dict]) -> list[str]:
    """根据题目内容推断需要哪些工具类别"""
    categories = set()
    for item in items:
        cat = item.get("category", "").lower()
        source = item.get("source", "").lower()
        if any(k in cat or k in source for k in ["chem", "atkins", "chemmc"]):
            categories.add("chemistry")
        if any(k in cat or k in source for k in ["phys", "thermo", "fund", "mechanics"]):
            categories.add("physics")
        if any(k in cat or k in source for k in ["math", "calculus", "diff", "stat"]):
            categories.add("math")

    # 默认加上 math 工具（通用计算器）
    categories.add("math")
    return list(categories)


def build_dataset(
    items: list[dict],
    name: str,
    system_prompt: str | None = None,
    tool_categories: list[str] | None = None,
    limit: int | None = None,
) -> dict:
    """构建完整的 eval_dataset 格式数据集"""
    dataset_type = detect_dataset_type(items)

    # 自动推断工具类别
    if tool_categories is None:
        tool_categories = detect_tools_needed(items)

    # 收集工具
    tools = []
    seen = set()
    for cat in tool_categories:
        for tool in TOOL_TEMPLATES.get(cat, []):
            if tool["name"] not in seen:
                tools.append(tool)
                seen.add(tool["name"])

    # 转换测试用例
    test_cases = []
    for i, item in enumerate(items):
        tc = convert_item(item, i, dataset_type)
        if tc:
            test_cases.append(tc)
        if limit and len(test_cases) >= limit:
            break

    # 系统提示词
    if system_prompt is None:
        system_prompt = DEFAULT_SYSTEM_PROMPTS.get(dataset_type, DEFAULT_SYSTEM_PROMPTS["scibench"])

    return {
        "name": name,
        "description": f"从 TTE 数据集转换: {name} ({len(test_cases)} 题, {len(tools)} 个工具)",
        "system_prompt": system_prompt,
        "tools": tools,
        "test_cases": test_cases,
    }


def main():
    parser = argparse.ArgumentParser(
        description="将 Test-Time-Tool-Evol 原始 JSON 转换为 eval_dataset 格式"
    )
    parser.add_argument(
        "input",
        help="输入的 JSON 文件或目录路径",
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="输出 JSON 文件路径 (默认: datasets/<name>_converted.json)",
    )
    parser.add_argument(
        "-n", "--limit",
        type=int,
        default=None,
        help="最多转换 N 道题",
    )
    parser.add_argument(
        "--tools",
        nargs="+",
        choices=["chemistry", "physics", "math"],
        default=None,
        help="附加工具类别 (默认: 自动推断)",
    )
    parser.add_argument(
        "--system-prompt",
        default=None,
        help="自定义系统提示词",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="数据集名称 (默认: 从文件名推断)",
    )
    parser.add_argument(
        "--no-tools",
        action="store_true",
        help="不附加工具（纯问答模式）",
    )
    args = parser.parse_args()

    input_path = args.input

    # 加载数据
    if os.path.isdir(input_path):
        items = load_tte_directory(input_path)
        default_name = Path(input_path).name
    elif os.path.isfile(input_path):
        items = load_tte_json(input_path)
        default_name = Path(input_path).stem
    else:
        print(f"错误: 找不到 {input_path}", file=sys.stderr)
        sys.exit(1)

    print(f"加载了 {len(items)} 条原始数据")

    # 数据集名称
    name = args.name or default_name

    # 工具
    if args.no_tools:
        tool_categories = []
    elif args.tools:
        tool_categories = args.tools
    else:
        tool_categories = None  # 自动推断

    # 转换
    dataset = build_dataset(
        items=items,
        name=name,
        system_prompt=args.system_prompt,
        tool_categories=tool_categories,
        limit=args.limit,
    )

    # 输出路径
    output_path = args.output
    if output_path is None:
        script_dir = Path(__file__).resolve().parent.parent
        output_path = str(script_dir / "datasets" / f"{name}_converted.json")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)

    print(f"\n转换完成:")
    print(f"  数据集名称: {dataset['name']}")
    print(f"  测试用例数: {len(dataset['test_cases'])}")
    print(f"  工具数量:   {len(dataset['tools'])}")
    print(f"  工具列表:   {[t['name'] for t in dataset['tools']]}")
    print(f"  输出文件:   {output_path}")


if __name__ == "__main__":
    main()
