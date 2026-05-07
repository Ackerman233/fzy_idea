# Black-Box Prompt Optimization - Tool Use Evaluation Demo

测试不同 System Prompt 在指导 LLM 调用工具时的表现，并对执行轨迹进行硬编码打分。

## 快速开始

```bash
cd /opt/data/private/src/fzy_idea

# 1. 创建 conda 虚拟环境 (Python 3.11)
conda create -n fzy python=3.11 -y
conda activate fzy

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置 API Key（已创建 .env 文件，填入你的 key）
# 编辑 .env 文件，将 OPENAI_API_KEY 设置为你的实际 key

# 4. 运行
python eval_demo.py
```

**激活环境**:
```bash
conda activate fzy
```

## 测试内容

**用户问题**: "帮我查一下北京今天的天气，然后告诉我如果气温乘以 5 是多少？"

**3 个 System Prompt 对比**:

| 风格 | 说明 |
|------|------|
| 极简风格 | 一句话指令，无额外约束 |
| CoT 思考风格 | 要求分步思考，明确工具依赖关系 |
| JSON 规划风格 | 要求先生成 JSON 执行计划再调用工具 |

**可用工具**:
- `get_weather(city)` — 查询天气（内置北京/上海/广州/深圳假数据）
- `calculate_math(expression)` — 数学计算器

## 打分规则 (满分 100)

| 维度 | 分值 | 评分逻辑 |
|------|------|----------|
| 工具选择 | +40 | 是否正确调用了 get_weather 和 calculate_math |
| 参数正确性 | +30 | 城市是否为北京、表达式是否包含 28 和 5 |
| 结果正确性 | +30 | 最终回答是否包含 28°C 和计算结果 140 |
| 冗余惩罚 | -10 | 调用不存在的工具或同一工具重复调用超过 2 次 |

打分器为纯硬编码 Python 函数，不依赖 LLM-as-a-judge，可直接改造为强化学习的 Reward Function。

## 输出示例

运行后会打印：
1. 每个 Prompt 的实时测试进度
2. 对比表格（工具调用次数、各项得分、总分）
3. 每个 Prompt 的详细打分明细和工具调用链

## 自定义

- 修改 `PROMPTS` 列表可添加更多 System Prompt 进行对比
- 修改 `MOCK_WEATHER_DATA` 可扩展城市数据
- 修改 `calculate_reward` 函数可调整打分逻辑
- 修改 `run_llm_with_tools` 中的 `model` 参数可切换模型（默认 `gpt-4o-mini`）
