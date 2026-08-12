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

# Open WebUI를 통해 Ollama 모델 연결
llm = ChatOpenAI(
    base_url=base_url_temp,
    api_key=api_key_temp,
    model=model_name_temp,
    temperature=0.7
)

# 질문 전달
response = llm.invoke(
    "LangChain을 쉽게 100자 이내로 설명해 주세요."
)

# 답변 출력
print(response.content)