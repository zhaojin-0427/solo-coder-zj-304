from typing import Any, Optional


def success_response(data: Any = None, message: str = "操作成功") -> dict:
    return {
        "code": 200,
        "message": message,
        "data": data
    }


def error_response(code: int = 400, message: str = "操作失败", data: Optional[Any] = None) -> dict:
    return {
        "code": code,
        "message": message,
        "data": data
    }


RISK_LEVELS = {
    "LOW": "低风险",
    "MEDIUM": "中风险",
    "HIGH": "高风险",
    "CRITICAL": "严重风险"
}


MEDICINE_TYPES = {
    "FEVER": "退烧药",
    "COLD": "感冒药",
    "COUGH": "止咳药",
    "ANTIDIARRHEAL": "止泻药",
    "ANTIBIOTIC": "抗生素",
    "VITAMIN": "维生素",
    "EXTERNAL": "外用药",
    "OTHER": "其他"
}


def get_age_label(months: int) -> str:
    if months < 1:
        return "新生儿"
    elif months < 12:
        return f"{months}月龄婴儿"
    elif months < 36:
        return f"{months // 12}岁{months % 12}个月幼儿"
    else:
        return f"{months // 12}岁儿童"
