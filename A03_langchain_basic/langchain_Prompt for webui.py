from langchain_core.prompts import ChatPromptTemplate
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

# 1. 프롬프트 템플릿 생성
prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "당신은 {level} 수준의 학습자에게 설명하는 교수입니다."
    ),
    (
        "human",
        "{topic}에 대해 예시를 포함하여 300자 내로 설명해 주세요."
    )
])


# 2. Open WebUI를 통해 Ollama/vLLM 모델 연결
llm = ChatOpenAI(
    base_url=base_url_temp,
    api_key=api_key_temp,
    model=model_name_temp,
    temperature=0.7,
    timeout=120
)


# 3. 템플릿 변수에 실제 값 입력
prompt_value = prompt.invoke({
    "level": "대학교 1학년",
    "topic": "생성형 인공지능"
})


# 4. ChatPromptValue를 메시지 목록으로 변환
messages = prompt_value.to_messages()


# 5. 생성된 메시지 확인
print("===== 모델에 전달되는 메시지 =====")

for message in messages:
    print(f"{type(message).__name__}: {message.content}")

print("================================")


# 6. Open WebUI에 메시지 전달
try:
    response = llm.invoke(messages)

    print("\n===== Open WebUI 답변 =====")
    print(response.content)
    print("===========================\n")

except Exception as error:
    print("\nOpen WebUI 연결 중 오류가 발생했습니다.")
    print(f"오류 내용: {error}")