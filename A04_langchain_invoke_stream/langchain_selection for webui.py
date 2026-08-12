from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
    AIMessage
)
from langchain_openai import ChatOpenAI

# 1. 환경 설정
import os
base_url_temp = os.getenv("OPENWEBUI_BASE_URL")
api_key_temp = os.getenv("OPENWEBUI_API_KEY")
model_name_temp = os.getenv("OPENWEBUI_MODEL")

if not base_url_temp:
    raise ValueError("OPENWEBUI_BASE_URL 환경변수가 없습니다.")

if not api_key_temp:
    raise ValueError("OPENWEBUI_API_KEY 환경변수가 없습니다.")

if not model_name_temp:
    raise ValueError("OPENWEBUI_MODEL 환경변수가 없습니다.")
# 환경 설정 종료

def invoke_chat(llm, messages):
    """전체 답변을 완성한 후 한 번에 출력합니다."""

    response = llm.invoke(messages)

    print("\n답변:")
    print(response.content)

    # 반환된 AIMessage를 대화 기록에 추가
    messages.append(response)


def stream_chat(llm, messages):
    """답변을 생성되는 즉시 화면에 출력합니다."""

    print("\n답변: ", end="", flush=True)

    full_response = ""

    for chunk in llm.stream(messages):
        if chunk.content:
            print(
                chunk.content,
                end="",
                flush=True
            )

            full_response += chunk.content

    print()

    # 여러 응답 조각을 하나의 AIMessage로 저장
    messages.append(
        AIMessage(content=full_response)
    )


def main():

    # Open WebUI 연결
    llm = ChatOpenAI(
        base_url=base_url_temp,
        api_key=api_key_temp,
        model=model_name_temp,
        temperature=0.7,
        timeout=120,
        max_retries=2
    )

    # 대화 기록 초기화
    messages = [
        SystemMessage(
            content=(
                "당신은 대학생에게 인공지능을 "
                "쉽게 설명하는 교수입니다."
            )
        )
    ]

    print("응답 방식을 선택하세요.")
    print("1. invoke 방식")
    print("2. stream 방식")

    mode = input("선택: ").strip()

    if mode not in {"1", "2"}:
        print("잘못된 선택입니다.")
        return

    print("\nOpen WebUI 대화를 시작합니다.")
    print("종료하려면 exit를 입력하세요.")

    while True:
        user_input = input("\n질문: ").strip()

        if user_input.lower() == "exit":
            print("프로그램을 종료합니다.")
            break

        if not user_input:
            print("질문을 입력해 주세요.")
            continue

        messages.append(
            HumanMessage(content=user_input)
        )

        try:
            if mode == "1":
                invoke_chat(llm, messages)
            else:
                stream_chat(llm, messages)

        except Exception as error:
            # 오류가 난 질문을 대화 기록에서 제거
            messages.pop()

            print("\n모델 호출 중 오류가 발생했습니다.")
            print(f"오류 내용: {error}")


if __name__ == "__main__":
    main()