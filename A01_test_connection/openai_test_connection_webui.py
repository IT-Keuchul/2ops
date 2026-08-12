import openai

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


# ==========================================
# Open WebUI 설정
# ==========================================

try:
    # OpenAI SDK가 자동으로 /chat/completions를 추가합니다.
    # 최종 호출 주소:
    client = openai.OpenAI(
        base_url=base_url_temp,
        api_key=api_key_temp,
        timeout=120.0
    )

    response = client.chat.completions.create(
        model=model_name_temp,
        messages=[
            {
                "role": "user",
                "content": (
                    "Open WebUI를 통한 Ollama 연결 테스트입니다. "
                    "'연결 성공'이라고 짧게 답하세요."
                )
            }
        ],
        stream=False
    )

    print("Open WebUI 연결 성공")
    print("사용 모델:", response.model)
    print("모델 응답:", response.choices[0].message.content)

except openai.AuthenticationError as error:
    print("인증 실패: Open WebUI API 키를 확인하세요.")
    print("오류:", error)

except openai.APIConnectionError as error:
    print("Open WebUI 서버에 연결할 수 없습니다.")
    print("주소:", OPEN_WEBUI_URL)
    print("오류:", error)

except openai.NotFoundError as error:
    print("API 경로 또는 모델을 찾을 수 없습니다.")
    print("모델명:", MODEL)
    print("오류:", error)

except openai.APIStatusError as error:
    print("Open WebUI가 오류를 반환했습니다.")
    print("상태 코드:", error.status_code)
    print("오류:", error)

except Exception as error:
    print("실행 중 오류가 발생했습니다.")
    print("오류 종류:", type(error).__name__)
    print("오류 내용:", error)