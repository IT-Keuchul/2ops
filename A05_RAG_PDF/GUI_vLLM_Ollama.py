import json
import os
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Optional

import requests
import urllib3

# 자체 서명된 SSL 인증서 경고 억제
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ============================================================
# 테마 및 디자인 설정 (Modern Pastel Light Theme)
# ============================================================
BG_DARK = "#E8EEF5"          # 메인 윈도우 배경 (부드러운 블루 그레이)
BG_PANEL = "#F4F8FB"         # 카드 및 패널 배경 (은은한 파스텔 블루-화이트)
BG_ENTRY = "#FFFFFF"         # 입력 폼 배경 (순백색)
BG_ENTRY_DISABLED = "#EBF1F6"# 입력 폼 비활성 배경 (연한 블루 그레이)
FG_DARK = "#1F2937"          # 주요 텍스트 색상 (짙은 그레이)
FG_MUTED = "#4B5563"         # 보조 텍스트 및 상태바 텍스트 (중간 그레이)
FG_PLACEHOLDER = "#9CA3AF"   # 입력 폼 플레이스홀더 회색 텍스트
BORDER_COLOR = "#BCD1E6"     # 스카이 블루 톤의 부드러운 테두리선 색상
BORDER_COLOR_ACTIVE = "#2563EB" # 활성화된 텍스트 필드 테두리선 색상

COLOR_ACCENT = "#2563EB"     # 메인 테마 블루
COLOR_ACCENT_HOVER = "#1D4ED8" # 호버 시 어두운 블루
FONT_FAMILY = "Malgun Gothic"


class OpenWebUIRAGApp:
    # 플레이스홀더 상수 정의
    PLACEHOLDER_URL = "input Open-Webui Url (/api 포함, 예: http://localhost:3000/api)"
    PLACEHOLDER_KEY = "Your Open-Webui API Key"
    PLACEHOLDER_MODEL = "Model_name"

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Open WebUI & vLLM PDF RAG Assistant")
        self.root.geometry("1180x870")
        self.root.configure(bg=BG_DARK)

        # 상태 변수
        self.msg_queue = queue.Queue()
        self.uploaded_file_id: Optional[str] = None
        self.uploaded_file_name: Optional[str] = None
        self.is_ready: bool = False
        self.chat_history = []  # 대화 내역 누적

        # UI 구성
        self.setup_styles()
        self.create_widgets()
        self.load_default_values()

        # 백그라운드 큐 모니터링
        self.root.after(100, self.process_queue)

    def setup_styles(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")

        self.style.configure(".", background=BG_DARK, foreground=FG_DARK, font=(FONT_FAMILY, 10))
        self.style.configure("TFrame", background=BG_DARK)
        self.style.configure("Panel.TFrame", background=BG_PANEL)
        self.style.configure("TLabel", background=BG_DARK, foreground=FG_DARK)
        self.style.configure("Panel.TLabel", background=BG_PANEL, foreground=FG_DARK, font=(FONT_FAMILY, 9, "bold"))
        self.style.configure("Header.TLabel", font=(FONT_FAMILY, 13, "bold"), background=BG_PANEL, foreground="#111827")
        self.style.configure("Status.TLabel", font=(FONT_FAMILY, 9), background=BG_DARK, foreground=FG_MUTED)

        # 메인 블루 버튼
        self.style.configure(
            "TButton",
            font=(FONT_FAMILY, 10, "bold"),
            background=COLOR_ACCENT,
            foreground="#FFFFFF",
            borderwidth=0,
            focuscolor="none"
        )
        self.style.map(
            "TButton",
            background=[("active", COLOR_ACCENT_HOVER), ("disabled", "#D1D5DB")],
            foreground=[("disabled", "#9CA3AF")]
        )

        # 보조 서브 버튼
        self.style.configure(
            "Sub.TButton",
            font=(FONT_FAMILY, 9),
            background=BG_DARK,
            foreground=FG_DARK,
            borderwidth=1,
            bordercolor=BORDER_COLOR
        )
        self.style.map(
            "Sub.TButton",
            background=[("active", "#D9E3EC"), ("disabled", BG_ENTRY_DISABLED)],
            foreground=[("disabled", "#9CA3AF")]
        )

    def set_placeholder(self, entry: tk.Entry, placeholder: str):
        """회색 글자 플레이스홀더를 Entry에 설정"""
        def on_focus_in(event):
            if entry.get() == placeholder:
                entry.delete(0, tk.END)
                entry.config(fg=FG_DARK)

        def on_focus_out(event):
            if not entry.get().strip():
                entry.delete(0, tk.END)
                entry.insert(0, placeholder)
                entry.config(fg=FG_PLACEHOLDER)

        entry.delete(0, tk.END)
        entry.insert(0, placeholder)
        entry.config(fg=FG_PLACEHOLDER)

        entry.bind("<FocusIn>", on_focus_in, add="+")
        entry.bind("<FocusOut>", on_focus_out, add="+")

    def get_entry_value(self, entry: tk.Entry, placeholder: str = "") -> str:
        """플레이스홀더가 아닌 실제 입력값만 반환"""
        val = entry.get().strip()
        if val == placeholder:
            return ""
        return val

    def create_widgets(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        main_frame = ttk.Frame(self.root, padding=12)
        main_frame.grid(row=0, column=0, sticky="nsew")
        main_frame.columnconfigure(0, weight=4)  # 좌측 설정창
        main_frame.columnconfigure(1, weight=7)  # 우측 대화창
        main_frame.rowconfigure(0, weight=1)

        # ============================================================
        # 좌측 설정 패널
        # ============================================================
        left_card = tk.Frame(
            main_frame,
            bg=BG_PANEL,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
            bd=0
        )
        left_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left_card.columnconfigure(0, weight=1)

        left_content = tk.Frame(left_card, bg=BG_PANEL, padx=18, pady=18)
        left_content.grid(row=0, column=0, sticky="nsew")
        left_content.columnconfigure(0, weight=1)

        lbl_title = ttk.Label(left_content, text="⚙️ Open WebUI & vLLM RAG", style="Header.TLabel")
        lbl_title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))

        self.row_idx = 1

        def create_entry_field(parent, label_text, is_file_btn=False, file_command=None, btn_text=""):
            lbl = ttk.Label(parent, text=label_text, style="Panel.TLabel")
            lbl.grid(row=self.row_idx, column=0, sticky="w", pady=(4, 2))
            self.row_idx += 1

            field_frame = tk.Frame(parent, bg=BG_PANEL)
            field_frame.grid(row=self.row_idx, column=0, sticky="ew", pady=(0, 5))
            field_frame.columnconfigure(0, weight=1)

            entry_container = tk.Frame(
                field_frame, 
                bg=BG_ENTRY, 
                highlightbackground=BORDER_COLOR, 
                highlightthickness=1, 
                bd=0
            )
            entry_container.grid(row=0, column=0, sticky="ew", padx=(0, 5 if is_file_btn else 0))
            entry_container.columnconfigure(0, weight=1)

            ent = tk.Entry(
                entry_container, 
                bg=BG_ENTRY, 
                fg=FG_DARK, 
                insertbackground=FG_DARK, 
                font=(FONT_FAMILY, 9),
                bd=0,
                relief="flat"
            )
            ent.grid(row=0, column=0, sticky="ew", ipady=4, padx=8)

            ent.bind("<FocusIn>", lambda e: entry_container.config(highlightbackground=BORDER_COLOR_ACTIVE), add="+")
            ent.bind("<FocusOut>", lambda e: entry_container.config(highlightbackground=BORDER_COLOR), add="+")

            if is_file_btn:
                btn = ttk.Button(field_frame, text=btn_text, style="Sub.TButton", command=file_command)
                btn.grid(row=0, column=1, sticky="ns")
                
            self.row_idx += 1
            return ent

        # 1. PDF 경로
        self.ent_pdf_path = create_entry_field(
            left_content, "PDF 파일 경로", is_file_btn=True, file_command=self.select_pdf_file, btn_text="파일 찾기"
        )
        # 2. Open WebUI URL
        self.ent_openwebui_url = create_entry_field(left_content, "Open WebUI Base URL (/api 포함)")
        # 3. Open WebUI API Key
        self.ent_openwebui_key = create_entry_field(left_content, "Open WebUI API Key (Bearer 토큰)")
        # 4. vLLM LLM 모델명
        self.ent_llm_model = create_entry_field(left_content, "vLLM LLM 모델명")

        # 안내 레이블 (임베딩 모델은 Open WebUI 관리자 설정에서 bge-m3로 자동 처리됨)
        info_frame = tk.Frame(left_content, bg="#EFF6FF", highlightbackground="#BFDBFE", highlightthickness=1, padx=10, pady=8)
        info_frame.grid(row=self.row_idx, column=0, sticky="ew", pady=(8, 12))
        self.row_idx += 1
        
        lbl_info = tk.Label(
            info_frame,
            text="💡 임베딩 안내:\nPDF를 업로드하면 Open WebUI 설정에 등록된\nvLLM BGE-M3 임베딩 엔진이 자동으로 호출되어\n문서 인덱싱을 수행합니다.",
            bg="#EFF6FF",
            fg="#1E40AF",
            font=(FONT_FAMILY, 8),
            justify="left"
        )
        lbl_info.pack(anchor="w")

        # 5. 파일 업로드 및 RAG 준비 실행 버튼
        self.btn_upload = ttk.Button(
            left_content, 
            text="🚀 PDF 업로드 및 RAG 인덱싱 시작", 
            command=self.start_file_upload
        )
        self.btn_upload.grid(row=self.row_idx, column=0, sticky="ew", ipady=8, pady=(0, 6))
        self.row_idx += 1

        # 6. 서버 등록 모델 목록 확인 버튼
        self.btn_check_models = ttk.Button(
            left_content,
            text="📋 서버 등록 모델 목록 확인",
            style="Sub.TButton",
            command=self.fetch_server_models
        )
        self.btn_check_models.grid(row=self.row_idx, column=0, sticky="ew", ipady=4)
        self.row_idx += 1

        # ============================================================
        # 우측 대화 패널
        # ============================================================
        right_panel = ttk.Frame(main_frame, style="TFrame")
        right_panel.grid(row=0, column=1, sticky="nsew")
        right_panel.columnconfigure(0, weight=1)
        right_panel.rowconfigure(0, weight=1)
        right_panel.rowconfigure(1, weight=0)

        # 대화창 영역
        chat_card = tk.Frame(
            right_panel,
            bg=BG_PANEL,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
            bd=0
        )
        chat_card.grid(row=0, column=0, sticky="nsew", pady=(0, 12))
        chat_card.columnconfigure(0, weight=1)
        chat_card.rowconfigure(0, weight=1)

        self.chat_area = ScrolledText(
            chat_card,
            wrap=tk.WORD,
            bg="#EBF2F7",
            fg=FG_DARK,
            insertbackground=FG_DARK,
            state=tk.DISABLED,
            font=(FONT_FAMILY, 10),
            padx=15,
            pady=15,
            borderwidth=0,
            highlightthickness=0,
            spacing2=4
        )
        self.chat_area.grid(row=0, column=0, sticky="nsew")

        # 대화 태그 스타일
        self.chat_area.tag_config(
            "system",
            background="#FEF3C7",
            foreground="#92400E",
            font=(FONT_FAMILY, 9, "bold"),
            spacing1=8,
            spacing3=8,
            lmargin1=15,
            lmargin2=15,
            rmargin=15
        )
        self.chat_area.tag_config(
            "user",
            background="#DBEAFE",
            foreground="#1E40AF",
            font=(FONT_FAMILY, 10, "bold"),
            spacing1=12,
            spacing3=6,
            lmargin1=15,
            lmargin2=15,
            rmargin=15
        )
        self.chat_area.tag_config(
            "ai",
            background="#FFFFFF",
            foreground=FG_DARK,
            font=(FONT_FAMILY, 10),
            spacing1=6,
            spacing2=4,
            spacing3=6,
            lmargin1=15,
            lmargin2=15,
            rmargin=15
        )
        self.chat_area.tag_config(
            "sources",
            background="#D1FAE5",
            foreground="#065F46",
            font=(FONT_FAMILY, 9, "italic"),
            spacing1=6,
            spacing3=12,
            lmargin1=15,
            lmargin2=15,
            rmargin=15
        )
        self.chat_area.tag_config(
            "error",
            background="#FEE2E2",
            foreground="#991B1B",
            font=(FONT_FAMILY, 9, "bold"),
            spacing1=8,
            spacing3=8,
            lmargin1=15,
            lmargin2=15,
            rmargin=15
        )

        # 질문 입력창
        input_card = tk.Frame(
            right_panel,
            bg=BG_PANEL,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
            bd=0
        )
        input_card.grid(row=1, column=0, sticky="ew")
        input_card.columnconfigure(0, weight=1)

        self.ent_question = tk.Entry(
            input_card,
            bg=BG_ENTRY,
            fg=FG_DARK,
            insertbackground=FG_DARK,
            font=(FONT_FAMILY, 10),
            bd=0,
            relief="flat"
        )
        self.ent_question.grid(row=0, column=0, sticky="ew", ipady=10, padx=12)
        self.ent_question.bind("<Return>", lambda event: self.start_asking())
        self.ent_question.bind("<FocusIn>", lambda e: input_card.config(highlightbackground=BORDER_COLOR_ACTIVE))
        self.ent_question.bind("<FocusOut>", lambda e: input_card.config(highlightbackground=BORDER_COLOR))

        self.btn_send = ttk.Button(input_card, text="질문 전송", command=self.start_asking, state=tk.DISABLED)
        self.btn_send.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=6)

        # 하단 상태바
        self.lbl_status = ttk.Label(self.root, text=" ⚠️ PDF 파일 업로드 및 RAG 준비가 필요합니다.", style="Status.TLabel", anchor="w", padding=6)
        self.lbl_status.grid(row=1, column=0, sticky="ew")

    # ============================================================
    # 기본값 및 헬퍼 함수
    # ============================================================
    def load_default_values(self):
        self.ent_pdf_path.insert(0, r"C:\rag\data\sample.pdf")
        self.set_placeholder(self.ent_openwebui_url, self.PLACEHOLDER_URL)
        self.set_placeholder(self.ent_openwebui_key, self.PLACEHOLDER_KEY)
        self.set_placeholder(self.ent_llm_model, self.PLACEHOLDER_MODEL)

    def select_pdf_file(self):
        file_path = filedialog.askopenfilename(
            title="PDF 파일 선택",
            filetypes=[("PDF 파일", "*.pdf"), ("모든 파일", "*.*")]
        )
        if file_path:
            self.ent_pdf_path.delete(0, tk.END)
            self.ent_pdf_path.insert(0, os.path.normpath(file_path))

    def write_to_chat(self, text: str, tag: str = "ai"):
        self.chat_area.config(state=tk.NORMAL)
        self.chat_area.insert(tk.END, text, tag)
        self.chat_area.config(state=tk.DISABLED)
        self.chat_area.see(tk.END)

    def update_status(self, text: str):
        self.lbl_status.config(text=text)

    def get_clean_base_url(self) -> str:
        url = self.get_entry_value(self.ent_openwebui_url, self.PLACEHOLDER_URL)
        if not url:
            return ""
        if not (url.startswith("http://") or url.startswith("https://")):
            url = "http://" + url
        url = url.rstrip("/")
        # 사용자가 /api를 포함해서 입력했더라도 중복 방지를 위해 공통 루트 URL로 정규화
        if url.endswith("/api"):
            url = url[:-4].rstrip("/")
        return url

    # ------------------------------------------------------------
    # 서버 모델 목록 확인 기능
    # ------------------------------------------------------------
    def fetch_server_models(self):
        base_url = self.get_clean_base_url()
        api_key = self.get_entry_value(self.ent_openwebui_key, self.PLACEHOLDER_KEY)

        if not base_url:
            messagebox.showwarning("입력 필요", "Open WebUI URL을 입력해주세요.\n(예: http://localhost:3000/api)")
            return

        self.write_to_chat(f"\n🔍 [System] 서버({base_url})의 등록된 모델 목록을 조회합니다...\n", "system")

        def run_fetch():
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            found_models = []
            
            # 1. Open WebUI /api/models 조회
            try:
                r = requests.get(f"{base_url}/api/models", headers=headers, timeout=10, verify=False)
                if r.status_code == 200:
                    data = r.json()
                    items = data if isinstance(data, list) else data.get("data", [])
                    for m in items:
                        name = m.get("id") or m.get("name")
                        if name and name not in found_models:
                            found_models.append(name)
            except Exception:
                pass

            # 2. Ollama /ollama/api/tags 조회
            try:
                r = requests.get(f"{base_url}/ollama/api/tags", headers=headers, timeout=10, verify=False)
                if r.status_code == 200:
                    data = r.json()
                    for m in data.get("models", []):
                        name = m.get("name") or m.get("model")
                        if name and name not in found_models:
                            found_models.append(name)
            except Exception:
                pass

            if found_models:
                models_text = "\n".join([f"  • {m}" for m in found_models])
                self.msg_queue.put(("log", f"서버에서 사용 가능한 모델 목록:\n{models_text}\n\n위 모델명 중 하나를 좌측 LLM 모델명 칸에 입력하세요.\n"))
            else:
                self.msg_queue.put(("log", "서버 모델 목록을 가져오지 못했습니다. (URL 또는 API Key 확인 필요)\n"))

        threading.Thread(target=run_fetch, daemon=True).start()

    # ------------------------------------------------------------
    # 1. 파일 업로드 및 Open WebUI 임베딩 처리 대기
    # ------------------------------------------------------------
    def start_file_upload(self):
        pdf_path_str = self.ent_pdf_path.get().strip()
        base_url = self.get_clean_base_url()
        api_key = self.get_entry_value(self.ent_openwebui_key, self.PLACEHOLDER_KEY)
        llm_model = self.get_entry_value(self.ent_llm_model, self.PLACEHOLDER_MODEL)

        if not pdf_path_str:
            messagebox.showwarning("입력 오류", "PDF 파일 경로를 선택해주세요.")
            return

        pdf_path = Path(pdf_path_str)
        if not pdf_path.exists():
            messagebox.showwarning("파일 없음", f"지정한 PDF 파일이 존재하지 않습니다:\n{pdf_path}")
            return

        if not base_url:
            messagebox.showwarning("입력 필요", "Open WebUI Base URL을 입력해주세요.\n(예: http://localhost:3000/api)")
            return

        if not api_key:
            messagebox.showwarning("API Key 필요", "Open WebUI 파일 업로드 및 RAG를 위해 API Key를 입력해주세요.\n(Open WebUI 설정 -> 계정 -> API 키)")
            return

        if not llm_model:
            messagebox.showwarning("입력 오류", "vLLM LLM 모델명을 입력해주세요.\n(예: gemma4:e4b, qwen3-8b 등)")
            return

        self.btn_upload.config(state=tk.DISABLED)
        self.btn_send.config(state=tk.DISABLED)
        self.update_status(" ⏳ Open WebUI로 PDF 업로드 및 vLLM BGE-M3 임베딩 처리 중...")
        self.write_to_chat(f"\n📤 [System] '{pdf_path.name}' 파일을 Open WebUI에 업로드합니다...\n", "system")

        thread = threading.Thread(
            target=self.upload_and_process_task,
            args=(pdf_path, base_url, api_key),
            daemon=True
        )
        thread.start()

    def upload_and_process_task(self, pdf_path: Path, base_url: str, api_key: str):
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            # 1. Open WebUI에 파일 업로드
            upload_url = f"{base_url}/api/v1/files/"
            self.msg_queue.put(("log", f"파일 업로드 요청: {upload_url}\n"))

            with open(pdf_path, "rb") as f:
                files = {"file": (pdf_path.name, f, "application/pdf")}
                r = requests.post(upload_url, headers=headers, files=files, timeout=60, verify=False)

            if r.status_code != 200:
                raise RuntimeError(f"파일 업로드 실패 (HTTP {r.status_code}):\n{r.text}")

            upload_data = r.json()
            file_id = upload_data.get("id")
            if not file_id:
                raise RuntimeError(f"응답에 파일 ID가 없습니다: {upload_data}")

            self.uploaded_file_id = file_id
            self.uploaded_file_name = pdf_path.name
            self.msg_queue.put(("log", f"파일 업로드 성공! (File ID: {file_id})\n"))
            self.msg_queue.put(("log", "Open WebUI 관리자 설정의 vLLM BGE-M3를 통해 임베딩을 계산 중입니다...\n"))

            # 2. 임베딩 및 문서 처리 완료 대기 (Polling status)
            status_url = f"{base_url}/api/v1/files/{file_id}/process/status"
            max_wait_seconds = 180
            start_time = time.time()
            is_completed = False

            while time.time() - start_time < max_wait_seconds:
                try:
                    res = requests.get(status_url, headers=headers, timeout=20, verify=False)
                    if res.status_code == 200:
                        status_data = res.json()
                        status = status_data.get("status")
                        self.msg_queue.put(("log_status", f" ⏳ 임베딩 상태: {status}..."))
                        
                        if status == "completed" or status is True:
                            is_completed = True
                            break
                        elif status == "failed":
                            raise RuntimeError(f"Open WebUI 임베딩 처리 실패:\n{status_data}")
                    elif res.status_code == 404:
                        # status 엔드포인트가 없을 경우 파일 상세 조회로 확인
                        file_info_url = f"{base_url}/api/v1/files/{file_id}"
                        res_info = requests.get(file_info_url, headers=headers, timeout=20, verify=False)
                        if res_info.status_code == 200:
                            info_data = res_info.json()
                            # data.get("data", {}).get("status") 등 확인
                            if info_data.get("data", {}).get("status") == "completed" or info_data.get("meta", {}).get("processed", False):
                                is_completed = True
                                break
                except Exception as poll_err:
                    self.msg_queue.put(("log", f"상태 확인 중 대기: {poll_err}\n"))

                time.sleep(2)

            # 약간의 여유 시간 후 준비 완료 처리
            self.msg_queue.put(("upload_success", f"'{pdf_path.name}'의 Open WebUI & vLLM BGE-M3 임베딩 인덱싱이 완료되었습니다."))

        except Exception as e:
            self.msg_queue.put(("upload_fail", str(e)))

    # ------------------------------------------------------------
    # 2. Open WebUI 파일 기반 RAG 질문 및 스트리밍 답변
    # ------------------------------------------------------------
    def start_asking(self):
        if not self.is_ready or not self.uploaded_file_id:
            messagebox.showwarning("경고", "먼저 PDF 파일을 업로드하고 RAG 인덱싱을 완료해주세요.")
            return

        question = self.ent_question.get().strip()
        if not question:
            return

        base_url = self.get_clean_base_url()
        api_key = self.get_entry_value(self.ent_openwebui_key, self.PLACEHOLDER_KEY)
        llm_model = self.get_entry_value(self.ent_llm_model, self.PLACEHOLDER_MODEL)

        # UI 상태 변경
        self.ent_question.delete(0, tk.END)
        self.btn_send.config(state=tk.DISABLED)
        self.ent_question.config(state=tk.DISABLED)
        self.update_status(" ⏳ Open WebUI & vLLM 모델이 답변을 생성하고 있습니다...")

        # 질문 화면 출력
        self.write_to_chat(f"\n\n🙋‍♂️ 질문: {question}\n", "user")
        self.write_to_chat("🤖 답변: ", "ai")

        # 대화 히스토리 추가
        self.chat_history.append({"role": "user", "content": question})

        # 비동기 질의 스레드
        thread = threading.Thread(
            target=self.ask_rag_task,
            args=(question, base_url, api_key, llm_model),
            daemon=True
        )
        thread.start()

    def ask_rag_task(self, question: str, base_url: str, api_key: str, llm_model: str):
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        # Open WebUI RAG 질의 페이로드 (files 필드에 업로드된 파일 ID 지정)
        payload = {
            "model": llm_model,
            "messages": self.chat_history,
            "files": [
                {
                    "type": "file",
                    "id": self.uploaded_file_id
                }
            ],
            "stream": True
        }

        chat_url = f"{base_url}/api/chat/completions"

        try:
            r = requests.post(chat_url, headers=headers, json=payload, stream=True, timeout=120, verify=False)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text}")

            full_answer = ""
            citations = []

            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue

                if line.startswith("data: "):
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break

                    try:
                        chunk_json = json.loads(data_str)
                        
                        # 텍스트 조각 추출
                        choices = chunk_json.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_answer += content
                                self.msg_queue.put(("answer_chunk", content))

                        # 출처(citations/sources) 정보 추출
                        if "citations" in chunk_json:
                            citations.extend(chunk_json["citations"])
                        if "sources" in chunk_json:
                            citations.extend(chunk_json["sources"])

                    except json.JSONDecodeError:
                        pass

            # AI 응답을 히스토리에 기록
            if full_answer:
                self.chat_history.append({"role": "assistant", "content": full_answer})

            self.msg_queue.put(("answer_done", citations))

        except Exception as e:
            self.msg_queue.put(("ask_fail", str(e)))

    # ------------------------------------------------------------
    # Queue 감시 및 UI 업데이트 루프
    # ------------------------------------------------------------
    def process_queue(self):
        while not self.msg_queue.empty():
            msg_type, data = self.msg_queue.get()

            if msg_type == "log":
                self.write_to_chat(f"⚙️ {data}", "system")
            elif msg_type == "log_status":
                self.update_status(data)
            elif msg_type == "upload_success":
                self.is_ready = True
                self.btn_upload.config(state=tk.NORMAL)
                self.btn_send.config(state=tk.NORMAL)
                self.ent_question.config(state=tk.NORMAL)
                self.ent_question.focus()
                self.update_status(f" ✅ RAG 준비 완료 ({self.uploaded_file_name})")
                self.write_to_chat(f"\n✅ {data}\n지금 PDF에 대해 질문해보세요!\n", "system")
                messagebox.showinfo("RAG 준비 완료", f"PDF 파일 업로드 및 인덱싱이 완료되었습니다!\n(File ID: {self.uploaded_file_id})")
            elif msg_type == "upload_fail":
                self.is_ready = False
                self.btn_upload.config(state=tk.NORMAL)
                self.update_status(" ❌ RAG 준비 실패")
                self.write_to_chat(f"\n❌ [Error] 업로드/인덱싱 중 오류 발생:\n{data}\n", "error")
                messagebox.showerror("업로드 오류", f"PDF 파일 업로드 또는 인덱싱에 실패했습니다:\n{data}")
            elif msg_type == "answer_chunk":
                self.write_to_chat(data, "ai")
            elif msg_type == "answer_done":
                if data:
                    # 출처 정보 표출
                    sources_desc = []
                    for s in data:
                        if isinstance(s, dict):
                            doc_name = s.get("source", {}).get("name", self.uploaded_file_name)
                            sources_desc.append(str(doc_name))
                        elif isinstance(s, str):
                            sources_desc.append(s)
                    if sources_desc:
                        self.write_to_chat(f"\n\n📄 [참고 문서: {', '.join(set(sources_desc))}]", "sources")
                
                self.btn_send.config(state=tk.NORMAL)
                self.ent_question.config(state=tk.NORMAL)
                self.ent_question.focus()
                self.update_status(f" ✅ RAG 준비 완료 ({self.uploaded_file_name})")
            elif msg_type == "ask_fail":
                self.write_to_chat(f"\n\n❌ [Error] 답변 생성 실패:\n{data}\n", "error")
                self.btn_send.config(state=tk.NORMAL)
                self.ent_question.config(state=tk.NORMAL)
                self.ent_question.focus()
                self.update_status(f" ✅ RAG 준비 완료 ({self.uploaded_file_name})")

        self.root.after(100, self.process_queue)


def main():
    root = tk.Tk()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = OpenWebUIRAGApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
