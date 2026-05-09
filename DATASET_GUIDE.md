# fzy_idea 数据集评估使用指南

## 概述

本文档记录如何将外部数据集接入 `fzy_idea/eval_dataset.py` 进行批量评估。目前支持两个数据源：

- **Test-Time-Tool-Evol (TTE)** — 科学计算题，共享工具集
- **ToolHop** — 多跳问答 benchmark，每题独立工具集

## 文件结构

```
fzy_idea/
├── eval_demo.py                  # 原有评估脚本（未修改）
├── eval_dataset.py               # 批量数据集评估脚本（支持 TTE + ToolHop）
├── tool_helpers.py               # 从 TTE 提取的工具函数集合
├── scripts/
│   ├── convert_tte_dataset.py    # TTE 原始 JSON → eval_dataset 格式转换
│   └── convert_toolhop.py        # ToolHop → eval_dataset 格式转换
├── datasets/
│   ├── scibench_sample.json      # scibench 科学计算题示例 (5题)
│   ├── scieval_sample.json       # scieval 科学选择题示例 (5题)
│   ├── scievo_sample.json        # scievo 进化数据集示例 (5题)
│   └── eval_demo_sample.json     # eval_demo 原有示例 (1题)
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
| `test_cases[].answer_type` | 否 | 答案类型（ToolHop 模式：`number`/`date`/`string`/`letter`） |
| `test_cases[].tools` | 否 | 每题独立工具列表（per-sample tools，格式同顶层 `tools`） |
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

### 5. ToolHop — 多跳工具调用 Benchmark

来源：`src/ToolHop/dataset/ToolHop.json`（995 道题）

ToolHop 是一个多跳问答 benchmark，测试 LLM 能否正确链式调用 3-7 个工具来回答复杂问题。每道题有**自己独立的工具集**（mock Python 函数），不同于 TTE 的共享工具模式。

**数据结构特点**：
- 每道题包含 `question`（多跳问题）、`answer`（标准答案）、`tools`（该题专用工具）、`functions`（工具的 Python 代码）
- 每个工具是一个完整的 Python 函数，包含硬编码的模拟逻辑，返回确定性结果
- 题目覆盖 62 个领域（Film、History、Mathematics、Genealogy 等）
- 答案类型：number (602)、date (165)、string (164)、letter (41) 等

**评估场景**（来自原始 benchmark）：

| 场景 | 说明 |
|------|------|
| `direct` | 不提供工具，模型直接回答（测试知识能力） |
| `mandatory` | 提供工具，系统提示要求必须调用工具（测试强制工具使用） |
| `free` | 提供工具，不限制是否使用（测试自愿工具使用） |

**打分方式**（精确匹配，与 TTE 的关键词匹配不同）：
1. 提取 `<answer>...</answer>` 标签中的内容
2. 先 `eval()` 数值比较，失败则大小写不敏感字符串匹配
3. 额外奖励：如果工具输出中包含标准答案，也算正确

示例题目：
```
How many letters (exclude the first and last) are there in the first name
of the person who designed Salisbury Woodland Gardens?

工具链: geo_relationship_finder → historical_figure_identifier
        → extract_first_name → count_letters
期望答案: 4
```

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

# 评估 ToolHop（先转换，再评估）
python3 scripts/convert_toolhop.py -n 20 --scenario free
python3 eval_dataset.py --dataset datasets/toolhop_free_20.json

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

评估脚本支持两种打分模式，根据数据集自动选择：

### TTE 模式（关键词匹配，满分 100）

当数据集没有 `answer_type` 字段时使用：

| 维度 | 分值 | 说明 |
|------|------|------|
| 关键词匹配 | 0-60 | 最终回答是否包含 `answer_keywords` 中的关键词 |
| 工具调用合理性 | 0-30 | 是否调用了可用工具、调用是否成功 |
| 冗余惩罚 | -10~0 | 调用不存在的工具 (-5) 或重复调用过多 (-5) |

选择题（单字母答案）会自动跳过工具调用评分，给满分 30。

### ToolHop 模式（精确匹配，0 或 100）

当数据集有 `answer_type` 字段时使用：

1. 提取 `<answer>...</answer>` 标签中的内容
2. 先尝试 `eval()` 数值比较（如 `4 == 4`）
3. 失败则大小写不敏感字符串比较（去掉 `.0` 后缀和逗号）
4. 额外奖励：如果最后一条工具响应中包含标准答案，也算正确

最终输出准确率 = 正确数 / 总题数 × 100%。

## 数据集转换脚本

### 从 Test-Time-Tool-Evol 转换

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

### 从 ToolHop 转换

使用 `scripts/convert_toolhop.py` 将 ToolHop benchmark 转换为 eval_dataset 格式。

```bash
cd /opt/data/private/src/fzy_idea

# 转换前 20 题，free 模式
python3 scripts/convert_toolhop.py -n 20 --scenario free

# 转换全部 995 题，mandatory 模式
python3 scripts/convert_toolhop.py --scenario mandatory -o datasets/toolhop_mandatory_full.json

# 转换 direct 模式（不提供工具，测试纯知识能力）
python3 scripts/convert_toolhop.py -n 50 --scenario direct
```

| 参数 | 说明 |
|------|------|
| `-i, --input` | ToolHop.json 路径（默认 `src/ToolHop/dataset/ToolHop.json`） |
| `-o, --output` | 输出路径（默认 `datasets/toolhop_<scenario>_<n>.json`） |
| `-n, --limit` | 只转换前 N 道题 |
| `--scenario` | 评估场景：`direct` / `mandatory` / `free`（默认 `free`） |
| `--name` | 数据集名称 |

转换后的 JSON 中，每道题的 `tools` 字段包含该题专用的工具列表（3-7 个），`eval_dataset.py` 会自动检测并使用 per-sample tools 模式。

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
