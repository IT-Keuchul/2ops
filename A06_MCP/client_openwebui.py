"""MCP 서버와 vLLM(또는 Open WebUI)을 연동하여 도구를 호출하는 클라이언트입니다.

- 사용자가 'exit', 'quit', 'q'를 입력할 때까지 계속해서 대화(루프)가 유지됩니다.
- vLLM 서버의 Tool Calling 옵션(--enable-auto-tool-choice)이 켜져 있는 경우:
  -> OpenAI 네이티브 Tool Calling으로 동작
- vLLM 서버의 Tool Calling 옵션이 꺼져 있는 경우:
  -> 프롬프트 기반 스마트 Fallback으로 자동 전환되어 MCP 도구들을 정상 호출
"""

import asyncio
import json
import os
import re
import sys
from pathlib import Path

# .env 파일이 존재하면 환경 변수를 불러옵니다.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import openai
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI

# 환경 변수에서 설정값을 가져옵니다.
BASE_URL = (
    os.getenv("OPENWEBUI_BASE_URL")
    or os.getenv("VLLM_BASE_URL")
)
API_KEY = (
    os.getenv("OPENWEBUI_API_KEY")
    or os.getenv("VLLM_API_KEY")
)
MODEL = (
    os.getenv("OPENWEBUI_MODEL")
    or os.getenv("VLLM_MODEL")
)


def mcp_tools_to_openai_tools(mcp_tools: list) -> list[dict]:
    """MCP 도구 목록을 OpenAI Function Calling 포맷으로 변환합니다."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema,
            },
        }
        for tool in mcp_tools
    ]


def tool_result_to_text(result) -> str:
    """MCP 도구 실행 결과에서 텍스트만 추출합니다."""
    texts: list[str] = []
    for item in result.content:
        if isinstance(item, types.TextContent):
            texts.append(item.text)
    return "\n".join(texts) if texts else str(result)


def extract_json_tool_call(content: str) -> dict | None:
    """모델의 일반 텍스트 응답에서 JSON 도구 호출 요청을 추출합니다."""
    # 1. ```json ... ``` 코드 블록 탐색
    code_block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if code_block_match:
        try:
            return json.loads(code_block_match.group(1))
        except json.JSONDecodeError:
            pass

    # 2. 텍스트 내 { "tool": ..., "arguments": ... } 또는 { "name": ..., "arguments": ... } 탐색
    bracket_match = re.search(r"(\{[\s\S]*\})", content)
    if bracket_match:
        try:
            data = json.loads(bracket_match.group(1))
            if isinstance(data, dict) and ("tool" in data or "name" in data or "function" in data):
                return data
        except json.JSONDecodeError:
            pass

    return None


async def run_prompt_fallback(
    llm_client: AsyncOpenAI,
    session: ClientSession,
    mcp_tools: list,
    question: str,
) -> None:
    """vLLM 서버에 tool-call-parser 옵션이 없을 때 프롬프트 기반으로 MCP 도구를 실행하는 Fallback 모드"""
    tools_desc = []
    for t in mcp_tools:
        tools_desc.append({
            "name": t.name,
            "description": t.description,
            "parameters": t.inputSchema,
        })

    system_prompt = (
        "You are an AI assistant equipped with tools.\n"
        "You MUST use tools for any calculation or robot movement commands.\n\n"
        "Available tools:\n"
        f"{json.dumps(tools_desc, ensure_ascii=False, indent=2)}\n\n"
        "If you need to call a tool, respond ONLY with a JSON object in this format:\n"
        "```json\n"
        "{\n"
        '  "tool": "<tool_name>",\n'
        '  "arguments": { "<arg_name>": <value>, ... }\n'
        "}\n"
        "```\n"
        "Do not include any conversational text before or after the JSON when invoking a tool."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    response = await llm_client.chat.completions.create(
        model=MODEL,
        messages=messages,
    )
    content = response.choices[0].message.content or ""

    tool_call_data = extract_json_tool_call(content)

    if tool_call_data:
        tool_name = tool_call_data.get("tool") or tool_call_data.get("name") or tool_call_data.get("function")
        tool_args = tool_call_data.get("arguments") or tool_call_data.get("parameters") or {}

        if isinstance(tool_args, str):
            try:
                tool_args = json.loads(tool_args)
            except json.JSONDecodeError:
                pass

        print(f"\n[모델의 도구 호출]")
        print(f"- 선택된 도구: {tool_name}")
        print(f"- 전달된 인자: {tool_args}")

        result = await session.call_tool(tool_name, arguments=tool_args)
        result_text = tool_result_to_text(result)

        print(f"- MCP 도구 실행 결과: {result_text}")

        messages.append({"role": "assistant", "content": content})
        messages.append({
            "role": "user",
            "content": f"[Tool Result for '{tool_name}']\n{result_text}\n\n위 도구 실행 결과를 바탕으로 사용자의 질문에 친절하게 최종 답변을 한국어로 작성해주세요.",
        })

        final_resp = await llm_client.chat.completions.create(
            model=MODEL,
            messages=messages,
        )
        print(f"\n최종 답변: {final_resp.choices[0].message.content}")
    else:
        print(f"\n최종 답변: {content}")


async def process_user_query(
    question: str,
    llm_client: AsyncOpenAI,
    session: ClientSession,
    mcp_tools: list,
    llm_tools: list,
) -> None:
    """사용자의 1회 질문에 대해 MCP 도구 호출 및 답변을 처리합니다."""
    messages = [
        {
            "role": "system",
            "content": (
                "당신은 도구(Tools)를 활용할 수 있는 AI 비서입니다.\n"
                "- 사칙연산(더하기, 빼기, 곱하기, 나누기) 질문에는 해당하는 계산 도구를 사용하세요.\n"
                "- 이동이나 방향 회전(전진, 후진, 좌회전, 우회전) 명령에는 해당하는 제어 도구를 사용하세요."
            ),
        },
        {"role": "user", "content": question},
    ]

    try:
        # 1차 요청: 네이티브 tools 시도
        first_response = await llm_client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=llm_tools,
        )
    except openai.BadRequestError as e:
        # vLLM 서버에 tool-call-parser가 없을 때 발생하는 400 에러를 Fallback 처리
        if "tool choice requires" in str(e) or "tool" in str(e).lower():
            await run_prompt_fallback(llm_client, session, mcp_tools, question)
            return
        raise e

    assistant_message = first_response.choices[0].message
    messages.append(assistant_message.model_dump(exclude_none=True))

    tool_calls = assistant_message.tool_calls or []

    if not tool_calls:
        print("\n최종 답변:", assistant_message.content)
        return

    # 모델이 요청한 MCP 도구 실행
    for tool_call in tool_calls:
        tool_name = tool_call.function.name
        tool_arguments = json.loads(tool_call.function.arguments)

        print(f"\n[모델의 도구 호출]")
        print(f"- 선택된 도구: {tool_name}")
        print(f"- 전달된 인자: {tool_arguments}")

        result = await session.call_tool(
            tool_name,
            arguments=tool_arguments,
        )
        result_text = tool_result_to_text(result)

        print(f"- MCP 도구 실행 결과: {result_text}")

        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result_text,
            }
        )

    # 2차 요청: 최종 답변 생성
    final_response = await llm_client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=llm_tools,
    )

    print(f"\n최종 답변: {final_response.choices[0].message.content}")


async def main() -> None:
    server_file = Path(__file__).with_name("mcp_server.py")

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(server_file)],
    )

    print("=" * 60)
    print(" [MCP & vLLM 도구 연동 대화형 클라이언트]")
    print(f"- Base URL : {BASE_URL}")
    print(f"- Model    : {MODEL}")
    print(" (종료하려면 'exit', 'quit', 또는 'q'를 입력하세요)")
    print("=" * 60)

    llm_client = AsyncOpenAI(
        base_url=BASE_URL,
        api_key=API_KEY,
    )

    # MCP 서버 실행 및 stdio 세션 연결
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            # MCP 서버에서 도구 목록을 조회
            tools_response = await session.list_tools()
            mcp_tools = tools_response.tools

            print(f"\n* MCP 서버에서 로드된 도구 ({len(mcp_tools)}개):")
            for t in mcp_tools:
                print(f"  - {t.name}: {t.description}")
            print("-" * 60)

            llm_tools = mcp_tools_to_openai_tools(mcp_tools)

            # exit 입력 전까지 지속적으로 반복 실행
            while True:
                try:
                    question = input("\n질문을 입력하세요: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n\n프로그램을 종료합니다.")
                    break

                if not question:
                    continue

                if question.lower() in ["exit", "quit", "q"]:
                    print("\n프로그램을 종료합니다. 이용해주셔서 감사합니다!")
                    break

                await process_user_query(
                    question=question,
                    llm_client=llm_client,
                    session=session,
                    mcp_tools=mcp_tools,
                    llm_tools=llm_tools,
                )


if __name__ == "__main__":
    asyncio.run(main())
