"""
Flight Transfer Tools - 航班中转查询工具（修复版）

提供根据始发地、中转地、目的地查询飞机中转方案。
使用本地城市字典和 searchFlightRoutes 替代不可靠的外部网站爬虫。
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging
import json

from .flight_search_tools import searchFlightRoutes
from ..utils.cities_dict import get_airport_code

# 初始化日志器
logger = logging.getLogger(__name__)


def getTransferFlightsByThreePlace(from_place: str, transfer_place: str, to_place: str, 
                                   min_transfer_time: float = 2.0,
                                   max_transfer_time: float = 5.0) -> Dict[str, Any]:
    """
    查询从出发地通过中转地到目的地的联程航班信息。
    
    修复说明：
    - 使用本地城市字典获取机场代码（替代外部网站爬虫）
    - 使用 searchFlightRoutes 查询航班（基于携程网页，稳定可靠）
    - 支持日期计算，自动查询第二段行程

    Args:
        from_place (str): 出发地城市或机场
        transfer_place (str): 中转地城市或机场
        to_place (str): 目的地城市或机场
        min_transfer_time (float): 最小中转时间（单位：小时），默认 2 小时
        max_transfer_time (float): 最大中转时间（单位：小时），默认 5 小时

    Returns:
        Dict: 包含中转航班查询结果的字典
    """
    logger.info(f"开始查询中转航班...")
    logger.info(f"始发地: {from_place}，中转地: {transfer_place}，目的地: {to_place}")
    logger.info(f"中转时间范围: {min_transfer_time}-{max_transfer_time} 小时")

    try:
        # 获取所有城市的机场代码（使用本地字典）
        from_code = get_airport_code(from_place)
        transfer_code = get_airport_code(transfer_place)
        to_code = get_airport_code(to_place)
        
        if not from_code or not transfer_code or not to_code:
            missing = []
            if not from_code:
                missing.append(from_place)
            if not transfer_code:
                missing.append(transfer_place)
            if not to_code:
                missing.append(to_place)
            return {
                "status": "error",
                "message": f"无法找到以下城市的机场代码: {', '.join(missing)}",
                "error_code": "INVALID_CITY"
            }

        logger.info(f"机场代码查询成功！始发地: {from_code}，中转地: {transfer_code}，目的地: {to_code}")

        # 使用今天的日期查询（中转查询通常查询当天可衔接的航班）
        today = datetime.now().strftime("%Y-%m-%d")
        
        # 获取第一段行程（出发地 -> 中转地）
        logger.info(f"查询第一段行程: {from_place} -> {transfer_place}")
        first_leg_result = searchFlightRoutes(from_place, transfer_place, today)
        
        if first_leg_result.get("status") != "success":
            return {
                "status": "error",
                "message": f"查询第一段行程失败: {first_leg_result.get('message', '未知错误')}",
                "error_code": "FIRST_LEG_FAILED"
            }
        
        first_leg_flights = first_leg_result.get("flights", [])
        if not first_leg_flights:
            return {
                "status": "success",
                "message": f"未找到 {from_place} 到 {transfer_place} 的直飞航班",
                "transfer_options": [],
                "transfer_count": 0
            }
        
        # 获取第二段行程（中转地 -> 目的地）
        logger.info(f"查询第二段行程: {transfer_place} -> {to_place}")
        second_leg_result = searchFlightRoutes(transfer_place, to_place, today)
        
        if second_leg_result.get("status") != "success":
            return {
                "status": "error",
                "message": f"查询第二段行程失败: {second_leg_result.get('message', '未知错误')}",
                "error_code": "SECOND_LEG_FAILED"
            }
        
        second_leg_flights = second_leg_result.get("flights", [])
        if not second_leg_flights:
            return {
                "status": "success",
                "message": f"未找到 {transfer_place} 到 {to_place} 的直飞航班",
                "transfer_options": [],
                "transfer_count": 0
            }
        
        logger.info(f"第一段找到 {len(first_leg_flights)} 个航班，第二段找到 {len(second_leg_flights)} 个航班")

        # 计算可行的中转组合
        transfer_options = []
        index = 1
        
        for first_flight in first_leg_flights:
            # 获取第一段到达时间
            arrival_time_str = first_flight.get("到达时间", "")
            if not arrival_time_str:
                continue
            
            # 解析到达时间（格式如 "23:40" 或 "07:35 +1天"）
            arrival_day_offset = 0
            if "+1天" in arrival_time_str:
                arrival_day_offset = 1
                arrival_time_str = arrival_time_str.replace(" +1天", "").strip()
            
            try:
                arrival_time = datetime.strptime(arrival_time_str, "%H:%M")
            except ValueError:
                continue
            
            for second_flight in second_leg_flights:
                # 获取第二段出发时间
                departure_time_str = second_flight.get("出发时间", "")
                if not departure_time_str:
                    continue
                
                # 解析出发时间
                try:
                    departure_time = datetime.strptime(departure_time_str, "%H:%M")
                except ValueError:
                    continue
                
                # 计算中转时间（考虑跨天）
                # 假设第二段航班在同一天或第二天
                for day_offset in [0, 1]:
                    second_departure = departure_time + timedelta(days=day_offset)
                    first_arrival = arrival_time + timedelta(days=arrival_day_offset)
                    
                    transfer_duration = (second_departure - first_arrival).total_seconds() / 3600
                    
                    # 检查是否满足中转时间要求
                    if min_transfer_time <= transfer_duration <= max_transfer_time:
                        transfer_option = {
                            "序号": index,
                            "第一段航班": {
                                "航班号": first_flight.get("航班号", ""),
                                "航空公司": first_flight.get("航空公司", ""),
                                "出发时间": first_flight.get("出发时间", ""),
                                "出发机场": first_flight.get("出发机场", ""),
                                "到达时间": first_flight.get("到达时间", ""),
                                "到达机场": first_flight.get("到达机场", ""),
                                "价格": first_flight.get("价格", "")
                            },
                            "第二段航班": {
                                "航班号": second_flight.get("航班号", ""),
                                "航空公司": second_flight.get("航空公司", ""),
                                "出发时间": second_flight.get("出发时间", ""),
                                "出发机场": second_flight.get("出发机场", ""),
                                "到达时间": second_flight.get("到达时间", ""),
                                "到达机场": second_flight.get("到达机场", ""),
                                "价格": second_flight.get("价格", "")
                            },
                            "中转信息": {
                                "中转城市": transfer_place,
                                "中转时间": f"{transfer_duration:.1f}小时",
                                "总价格": f"{first_flight.get('价格', '').replace('起', '').replace('¥', '')} + {second_flight.get('价格', '').replace('起', '').replace('¥', '')}"
                            }
                        }
                        transfer_options.append(transfer_option)
                        index += 1
                        logger.info(f"找到中转方案 #{index-1}: {first_flight.get('航班号')} -> {second_flight.get('航班号')}, 中转时间: {transfer_duration:.1f}小时")
                        break  # 找到一个合适的日期偏移即可
        
        # 按价格排序
        def extract_price(option):
            try:
                price_str = option["第一段航班"]["价格"].replace("¥", "").replace("起", "").strip()
                return int(price_str)
            except:
                return 999999
        
        transfer_options.sort(key=extract_price)
        
        logger.info(f"共找到 {len(transfer_options)} 条中转方案")
        
        return {
            "status": "success",
            "from": from_place,
            "transfer": transfer_place,
            "to": to_place,
            "transfer_count": len(transfer_options),
            "transfer_options": transfer_options,
            "formatted_output": _format_transfer_result(transfer_options, from_place, transfer_place, to_place),
            "query_time": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"查询中转航班失败：{str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"查询中转航班失败: {str(e)}",
            "error_code": "TRANSFER_SEARCH_FAILED"
        }


def _format_transfer_result(transfer_options: List[Dict], from_place: str, transfer_place: str, to_place: str) -> str:
    """
    格式化中转航班查询结果
    """
    if not transfer_options:
        return f"😔 未找到 {from_place} -> {transfer_place} -> {to_place} 的合适中转方案"
    
    output = []
    output.append(f"✈️ 中转航班查询结果")
    output.append(f"📍 {from_place} -> {transfer_place} -> {to_place}")
    output.append(f"🔢 共找到 {len(transfer_options)} 条中转方案")
    output.append("")
    
    for i, option in enumerate(transfer_options[:10], 1):  # 最多显示10条
        first = option["第一段航班"]
        second = option["第二段航班"]
        transfer = option["中转信息"]
        
        output.append(f"【方案 {i}】")
        output.append(f"  第一段: {first['航空公司']} {first['航班号']}")
        output.append(f"    🛫 {first['出发时间']} {first['出发机场']}")
        output.append(f"    🛬 {first['到达时间']} {first['到达机场']}")
        output.append(f"    💰 {first['价格']}")
        output.append(f"  中转: ⏱️ {transfer['中转时间']} @ {transfer_place}")
        output.append(f"  第二段: {second['航空公司']} {second['航班号']}")
        output.append(f"    🛫 {second['出发时间']} {second['出发机场']}")
        output.append(f"    🛬 {second['到达时间']} {second['到达机场']}")
        output.append(f"    💰 {second['价格']}")
        output.append("")
    
    return "\n".join(output)


if __name__ == '__main__':
    # 测试示例
    print("开始查询中转航班（北京-上海-成都）")
    results = getTransferFlightsByThreePlace("北京", "上海", "成都", min_transfer_time=2.0, max_transfer_time=6.0)
    print(json.dumps(results, indent=2, ensure_ascii=False))
