# Test-Time-Tool-Evol 数据集接入 fzy_idea 使用指南

## 概述

本文档记录如何将 `Test-Time-Tool-Evol` 项目的数据集接入 `fzy_idea/eval_demo` 进行评估。

## 文件结构

```
fzy_idea/
├── eval_demo.py                  # 原有评估脚本（未修改）
├── eval_dataset.py               # 新建：批量数据集评估脚本
├── tool_helpers.py               # 新建：从 Test-Time-Tool-Evol 提取的工具函数集合
├── scripts/
│   └── convert_tte_dataset.py    # 新建：TTE 原始 JSON → eval_dataset 格式转换脚本
├── datasets/
│   ├── scibench_sample.json      # 新建：scibench 科学计算题示例 (5题)
│   ├── scieval_sample.json       # 新建：scieval 科学选择题示例 (5题)
│   ├── scievo_sample.json        # 新建：scievo 进化数据集示例 (5题)
│   └── eval_demo_sample.json     # 新建：eval_demo 原有示例 (1题)
└── DATASET_GUIDE.md              # 本文件
```

## JSON 数据集格式

每个 JSON 数据集文件包含以下字段：

```json
{
  "name": "数据集名称",
  "description": "描述",
  "system_prompt": "系统提示词",
  "tools": [
    {
      "name": "函数名",
      "description": "函数描述",
      "code": "def func_name(...): ...",
      "parameters": {
        "type": "object",
        "properties": {
          "param1": {"type": "string", "description": "参数描述"}
        },
        "required": ["param1"]
      }
    }
  ],
  "test_cases": [
    {
      "id": "唯一ID",
      "question": "用户问题",
      "expected_answer": "标准答案",
      "answer_keywords": ["关键词1", "关键词2"],
      "source": "来源数据集",
      "category": "类别"
    }
  ]
}
```

### 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | 是 | 数据集名称 |
| `description` | 否 | 数据集描述 |
| `system_prompt` | 是 | 发给 LLM 的系统提示词 |
| `tools[].name` | 是 | 工具函数名（需与 code 中的函数名一致） |
| `tools[].description` | 是 | 工具描述，LLM 根据此描述决定是否调用 |
| `tools[].code` | 是 | 完整的 Python 函数代码，运行时通过 exec() 加载 |
| `tools[].parameters` | 是 | OpenAI function-calling 的 parameters schema |
| `test_cases[].id` | 是 | 测试用例唯一 ID |
| `test_cases[].question` | 是 | 用户问题 |
| `test_cases[].expected_answer` | 是 | 标准答案 |
| `test_cases[].answer_keywords` | 否 | 关键词列表，用于模糊匹配打分 |
| `test_cases[].source` | 否 | 来源数据集路径 |
| `test_cases[].category` | 否 | 题目类别 |

## 数据集来源

### 1. scibench_sample.json — 科学计算题

来源：`Test-Time-Tool-Evol/dataset/scibench/`

包含物理、化学、数学计算题，匹配的工具：
- `count_atoms` — 计算分子式中各类原子的数量
- `count_hydrogen_atoms` — 计算氢原子数量
- `count_oxygen_atoms` — 计算氧原子数量
- `calculate_thrust_force` — 计算火箭推力
- `calculate_math` — 数学表达式计算

示例题目：
```
Calculate the de Broglie wavelength for an electron with a kinetic energy of 100 eV.
期望答案: 0.123
```

### 2. scieval_sample.json — 科学选择题

来源：`Test-Time-Tool-Evol/dataset/scieval/`

包含生物、化学、物理选择题，LLM 直接回答，无需工具调用。

示例题目：
```
What does spectroscopy tell us?
A. Spectroscopy calculates the boiling points...
B. Infrared spectroscopy helps identify the color...
C. Infrared spectroscopy reveals information about bonds...
D. Spectroscopy measures the speed of light...
期望答案: C
```

### 3. scievo_sample.json — 进化数据集

来源：`Test-Time-Tool-Evol/dataset/scievo/`

包含化学、物理计算题，用于工具进化验证。工具与 scibench 类似。

示例题目：
```
Suppose that 10.0 mol C2H6(g) is confined to 4.860 dm^3 at 27°C.
Predict the pressure exerted by the ethane from the perfect gas.
期望答案: 50.7
```

### 4. eval_demo_sample.json — 基准对照

来源：`fzy_idea/eval_demo.py` 原有的天气+计算示例，用于对比验证。

## 使用方法

### 前置条件

```bash
cd /opt/data/private/src/fzy_idea
pip install -r requirements.txt  # openai, python-dotenv, rich
```

确保 `.env` 文件中配置了 API 密钥：
```
OPENAI_API_KEY=your_key_here
OPENAI_BASE_URL=https://your-api-endpoint/v1
MODEL_NAME=your-model-name
```

### 运行评估

```bash
# 评估 scibench 数据集
python3 eval_dataset.py --dataset datasets/scibench_sample.json

# 评估 scieval 数据集
python3 eval_dataset.py --dataset datasets/scieval_sample.json

# 评估 scievo 数据集
python3 eval_dataset.py --dataset datasets/scievo_sample.json

# 评估 eval_demo 原有示例
python3 eval_dataset.py --dataset datasets/eval_demo_sample.json

# 指定模型
python3 eval_dataset.py --dataset datasets/scibench_sample.json --model gpt-4o

# 只评估前 2 题
python3 eval_dataset.py --dataset datasets/scibench_sample.json --limit 2
```

### 输出示例

```
数据集评估报告: scibench_sample
┌────────────────────┬────────┬──────────┬──────────────┬──────────────┬──────────┬──────┬──────────────────────────┐
│ ID                 │ 类别   │ 工具调用 │ 关键词匹配   │ 工具合理性   │ 冗余惩罚 │ 总分 │ 最终回答 (截断)          │
│                    │        │          │ (满分60)     │ (满分30)     │          │      │                          │
├────────────────────┼────────┼──────────┼──────────────┼──────────────┼──────────┼──────┼──────────────────────────┤
│ scibench_chemmc_1  │ chem   │ 1        │ 60/60        │ 30/30        │ 0        │ 90   │ The de Broglie wavelen... │
│ scibench_chemmc_2  │ chem   │ 0        │ 60/60        │ 30/30        │ 0        │ 90   │ The work function is 3... │
└────────────────────┴────────┴──────────┴──────────────┴──────────────┴──────────┴──────┴──────────────────────────┘

汇总:
  总题数: 2
  平均分: 90.0/100
  及格率 (>=60分): 2/2 (100%)
```

## 打分机制

评估脚本使用三维度打分，满分 100：

| 维度 | 分值 | 说明 |
|------|------|------|
| 关键词匹配 | 0-60 | 最终回答是否包含 `answer_keywords` 中的关键词 |
| 工具调用合理性 | 0-30 | 是否调用了可用工具、调用是否成功 |
| 冗余惩罚 | -10~0 | 调用不存在的工具 (-5) 或重复调用过多 (-5) |

选择题（单字母答案）会自动跳过工具调用评分，给满分 30。

## 从 Test-Time-Tool-Evol 批量转换

使用 `scripts/convert_tte_dataset.py` 可以直接从原始 TTE JSON 文件转换为 eval_dataset 格式。

### 基本用法

```bash
cd /opt/data/private/src/fzy_idea

# 转换单个文件（取前 10 题）
python3 scripts/convert_tte_dataset.py /path/to/scibench/cal_calculus.json -n 10

# 转换整个目录
python3 scripts/convert_tte_dataset.py /path/to/scibench/ --name scibench_all -n 20

# 转换 scieval 选择题
python3 scripts/convert_tte_dataset.py /path/to/scieval/scieval_che.json --name scieval_chem -n 10
```

### 参数说明

| 参数 | 说明 |
|------|------|
| `input` | 输入的 JSON 文件或目录路径 |
| `-o, --output` | 输出路径（默认 `datasets/<name>_converted.json`） |
| `-n, --limit` | 最多转换 N 道题 |
| `--tools` | 指定工具类别：`chemistry`, `physics`, `math`（默认自动推断） |
| `--no-tools` | 不附加工具（纯问答模式） |
| `--name` | 数据集名称 |
| `--system-prompt` | 自定义系统提示词 |

### 自动推断

脚本会根据题目内容自动推断：
- **数据集类型**：scibench（计算题）、scieval（选择题）、scievo
- **工具类别**：根据 `category` 和 `source` 字段判断需要 chemistry/physics/math 工具
- **系统提示词**：根据数据集类型选择合适的提示词

### 示例

```bash
# scibench 物理题 + 物理工具
python3 scripts/convert_tte_dataset.py /data/scibench/cal_thermo.json --tools physics math -n 10

# scieval 选择题，不附加工具
python3 scripts/convert_tte_dataset.py /data/scieval/scieval_bio.json --no-tools -n 20

# 转换整个 scievo 目录，自定义提示词
python3 scripts/convert_tte_dataset.py /data/scievo/ --name scievo_full \
  --system-prompt "你是一个科学计算助手，请调用工具并给出精确答案。"
```

## 工具函数来源

`tool_helpers.py` 中的工具函数提取自：
- `Test-Time-Tool-Evol/dataset/adapt_tools/chemistry_tools_library_evolve.json` — 化学工具
- `Test-Time-Tool-Evol/dataset/adapt_tools/phys_tools_library_evolve.json` — 物理工具
- `fzy_idea/eval_demo.py` — 原有天气和数学工具

这些函数也可以在其他脚本中直接导入使用：
```python
from tool_helpers import TOOL_REGISTRY
result = TOOL_REGISTRY["count_atoms"]("C6H12O6")
```
