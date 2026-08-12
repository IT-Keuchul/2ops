from openai import OpenAI

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

# OpenAI SDK가 자동으로 /chat/completions를 추가합니다.
# 최종 호출 주소:
client = OpenAI(
        base_url=base_url_temp,
        api_key=api_key_temp,
        timeout=120.0
)

while True:
    mes = input('입력하삼 : ')
    if mes == 'exit':
        break
    # 2. 실행 중인 Ollama 모델 이름을 입력하여 요청을 보냅니다.
    response = client.chat.completions.create(
        model=model_name_temp,  # PC에 다운로드 받아둔 모델명 입력
        messages=[
            {"role": "user", "content": mes}
        ]
    )

    print(response.choices[0].message.content)

    # 3. OpenAI 응답 객체에서 토큰 정보 추출
    usage = response.usage
    prompt_tokens = usage.prompt_tokens          # 입력 토큰 수
    output_tokens = usage.completion_tokens      # 출력 토큰 (답변) 수
    total_tokens = usage.total_tokens            # 전체 토큰 수

    # 4. 결과 출력
    print("\n===== OpenAI 사용량 =====")
    print(f"입력 토큰 수: {prompt_tokens}")
    print(f"출력 토큰 수: {output_tokens}")
    print(f"전체 토큰 수: {total_tokens}")
    print("========================\n")