"""계산기 및 로봇/이동 제어 도구를 제공하는 FastMCP 서버 예제입니다.

도구 목록:
1. 계산: add(더하기), subtract(빼기), multiply(곱하기), divide(나누기)
2. 제어: move_forward(전진), move_backward(후진), turn_right(오른쪽 회전), turn_left(왼쪽 회전)
"""

from mcp.server import MCPServer

# MCP 서버 객체 생성
mcp = MCPServer("Enhanced Controller & Calculator")


# ==========================================
# 1. 사칙연산 도구
# ==========================================

@mcp.tool()
def add(a: float, b: float) -> float:
    """두 수를 더합니다.

    Args:
        a: 첫 번째 수
        b: 두 번째 수
    """
    return a + b


@mcp.tool()
def subtract(a: float, b: float) -> float:
    """첫 번째 수에서 두 번째 수를 뺍니다.

    Args:
        a: 첫 번째 수
        b: 두 번째 수
    """
    return a - b


@mcp.tool()
def multiply(a: float, b: float) -> float:
    """두 수를 곱합니다.

    Args:
        a: 첫 번째 수
        b: 두 번째 수
    """
    return a * b


@mcp.tool()
def divide(a: float, b: float) -> str:
    """첫 번째 수를 두 번째 수로 나눕니다.

    Args:
        a: 분자 (나누어지는 수)
        b: 분모 (나누는 수)
    """
    if b == 0:
        return "오류: 0으로 나눌 수 없습니다."
    return str(a / b)


# ==========================================
# 2. 이동 및 회전 제어 도구
# ==========================================

@mcp.tool()
def move_forward(distance: float = 1.0) -> str:
    """전진 명령을 수행합니다.

    Args:
        distance: 전진할 거리 (기본값: 1.0m)
    """
    return f"[제어 명령] 전진(move_forward) 명령을 인식했습니다. (이동 거리: {distance}m)"


@mcp.tool()
def move_backward(distance: float = 1.0) -> str:
    """후진 명령을 수행합니다.

    Args:
        distance: 후진할 거리 (기본값: 1.0m)
    """
    return f"[제어 명령] 후진(move_backward) 명령을 인식했습니다. (이동 거리: {distance}m)"


@mcp.tool()
def turn_right(angle: float = 90.0) -> str:
    """오른쪽 방향으로 회전 명령을 수행합니다.

    Args:
        angle: 회전할 각도(도 단위, 기본값: 90도)
    """
    return f"[제어 명령] 오른쪽 방향으로 회전(turn_right) 명령을 인식했습니다. (회전 각도: {angle}도)"


@mcp.tool()
def turn_left(angle: float = 90.0) -> str:
    """왼쪽 방향으로 회전 명령을 수행합니다.

    Args:
        angle: 회전할 각도(도 단위, 기본값: 90도)
    """
    return f"[제어 명령] 왼쪽 방향으로 회전(turn_left) 명령을 인식했습니다. (회전 각도: {angle}도)"


if __name__ == "__main__":
    # stdio 방식으로 MCP 서버 구동
    mcp.run(transport="stdio")
