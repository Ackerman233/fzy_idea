"""
从 Test-Time-Tool-Evol 的 adapt_tools 中提取的工具函数集合
以及 eval_demo 原有的工具函数
"""

import json
import math
import re


# ============================================================================
# 化学工具 (来自 chemistry_tools_library_evolve.json)
# ============================================================================

def count_hydrogen_atoms(molecular_formula: str) -> str:
    """计算分子式中氢原子的数量"""
    if 'H' not in molecular_formula:
        return json.dumps({"result": 0})
    h_index = molecular_formula.find('H')
    num_str = ""
    for i in range(h_index + 1, len(molecular_formula)):
        if molecular_formula[i].isdigit():
            num_str += molecular_formula[i]
        else:
            break
    count = int(num_str) if num_str else 1
    return json.dumps({"result": count})


def count_oxygen_atoms(molecular_formula: str) -> str:
    """计算分子式中氧原子的数量"""
    if 'O' not in molecular_formula:
        return json.dumps({"result": 0})
    o_index = molecular_formula.find('O')
    num_str = ""
    for i in range(o_index + 1, len(molecular_formula)):
        if molecular_formula[i].isdigit():
            num_str += molecular_formula[i]
        else:
            break
    count = int(num_str) if num_str else 1
    return json.dumps({"result": count})


def count_sulfur_atoms(formula: str) -> str:
    """计算分子式中硫原子的数量"""
    if 'S' not in formula:
        return json.dumps({"result": 0})
    s_index = formula.find('S')
    num_str = ""
    for i in range(s_index + 1, len(formula)):
        if formula[i].isdigit():
            num_str += formula[i]
        else:
            break
    count = int(num_str) if num_str else 1
    return json.dumps({"result": count})


def count_atoms(molecular_formula: str) -> str:
    """计算分子式中各类原子的数量"""
    pattern = r'([A-Z][a-z]*)([0-9]*)'
    matches = re.findall(pattern, molecular_formula)
    atom_counts = {}
    for element, count in matches:
        if element:
            atom_counts[element] = int(count) if count else 1
    return json.dumps({"result": atom_counts})


def extract_hydrogen_atoms(formula: str) -> str:
    """从化学式中提取氢原子的数量"""
    match = re.search(r'H(\d+)', formula)
    if match:
        count = int(match.group(1))
    elif 'H' in formula:
        count = 1
    else:
        count = 0
    return json.dumps({"result": count})


def calculate_molecule_mass(molar_mass: float) -> str:
    """将摩尔质量转换为单个分子的质量 (kg)"""
    avogadro_number = 6.02214076e23
    molecule_mass = molar_mass / avogadro_number
    return json.dumps({"result": f"{molecule_mass:.3e} kg"})


# ============================================================================
# 物理工具 (来自 phys_tools_library_evolve.json)
# ============================================================================

def calculate_thrust_force(fuel_burn_rate: float, exhaust_velocity: float) -> str:
    """计算火箭产生的推力 (N)"""
    thrust_force = fuel_burn_rate * exhaust_velocity
    return json.dumps({"result": f"{thrust_force:.6e} N"})


def calculate_net_force(thrust_force: float, gravitational_force: float) -> str:
    """计算作用在火箭上的净力 (N)"""
    net_force = thrust_force - gravitational_force
    return json.dumps({"result": f"{net_force:.6e} N"})


def check_immediate_liftoff(net_force: float) -> str:
    """检查火箭是否立即起飞"""
    return json.dumps({"result": net_force > 0})


def calculate_liftoff_time(initial_mass: float, fuel_burn_rate: float,
                           thrust_force: float, gravity: float = 9.81) -> str:
    """计算火箭起飞所需时间 (s)"""
    liftoff_time = (initial_mass - thrust_force / gravity) / fuel_burn_rate
    return json.dumps({"result": f"{liftoff_time:.6e} s"})


def calculate_delta_v(exhaust_velocity: float, initial_mass: float,
                      fuel_mass: float) -> str:
    """使用齐奥尔科夫斯基火箭方程计算速度变化 (m/s)"""
    final_mass = initial_mass - fuel_mass
    delta_v = exhaust_velocity * math.log(initial_mass / final_mass)
    return json.dumps({"result": f"{delta_v:.6e} m/s"})


def calculate_coriolis_deflection(f: float, v_x: float,
                                   time_of_flight: float) -> str:
    """计算科里奥利力导致的水平偏移 (m)"""
    deflection = 0.5 * f * v_x * time_of_flight ** 2
    return json.dumps({"result": f"{deflection:.5e} m"})


# ============================================================================
# eval_demo 原有工具
# ============================================================================

MOCK_WEATHER_DATA = {
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
    sanitized = re.sub(r"[^0-9+\-*/().%\s]", "", expression)
    if not sanitized.strip():
        return json.dumps({"error": "无效的数学表达式"}, ensure_ascii=False)
    try:
        result = eval(sanitized)  # noqa: S307
        return json.dumps({"expression": expression, "result": result}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"计算失败: {str(e)}"}, ensure_ascii=False)


# ============================================================================
# 工具注册表：名称 -> 函数
# ============================================================================

TOOL_REGISTRY = {
    # 化学
    "count_hydrogen_atoms": count_hydrogen_atoms,
    "count_oxygen_atoms": count_oxygen_atoms,
    "count_sulfur_atoms": count_sulfur_atoms,
    "count_atoms": count_atoms,
    "extract_hydrogen_atoms": extract_hydrogen_atoms,
    "calculate_molecule_mass": calculate_molecule_mass,
    # 物理
    "calculate_thrust_force": calculate_thrust_force,
    "calculate_net_force": calculate_net_force,
    "check_immediate_liftoff": check_immediate_liftoff,
    "calculate_liftoff_time": calculate_liftoff_time,
    "calculate_delta_v": calculate_delta_v,
    "calculate_coriolis_deflection": calculate_coriolis_deflection,
    # eval_demo 原有
    "get_weather": get_weather,
    "calculate_math": calculate_math,
}
