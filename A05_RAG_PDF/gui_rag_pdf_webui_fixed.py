import json
import queue
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from urllib.parse import quote

import requests

PAGE_SIZE = 50


APP_TITLE = "Open WebUI PDF RAG Assistant"
DEFAULT_MODEL = "qwen3.6-35b-a3b"
REQUEST_TIMEOUT = 120
PROCESS_TIMEOUT = 600

BG = "#E8EEF5"
PANEL = "#F4F8FB"
WHITE = "#FFFFFF"
TEXT = "#1F2937"
MUTED = "#4B5563"
BLUE = "#2563EB"
RED = "#B91C1C"
FONT = "Malgun Gothic"


def human_size(value):
    try:
        size = float(value or 0)
    except (TypeError, ValueError):
        return "-"
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


def human_date(value):
    if value in (None, ""):
        return "-"
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            return datetime.fromtimestamp(float(value)).strftime("%Y-%m-%d %H:%M")
        return str(value).replace("T", " ")[:16]
    except Exception:
        return str(value)


def normalize_webui_url(value: str) -> str:
    """입력값을 http(s)://호스트[:포트] 형태로 정리하되, 사용자가 입력한 /api는 유지합니다."""
    url = value.strip()
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    return url.rstrip("/")


def response_error(response: requests.Response, action: str) -> RuntimeError:
    """Open WebUI 오류 응답을 읽기 쉬운 메시지로 바꿉니다."""
    try:
        detail = response.json()
    except ValueError:
        detail = response.text
    return RuntimeError(f"{action} 실패 (HTTP {response.status_code})\n{detail}")


class OpenWebUIClient:
    """Open WebUI의 파일 RAG API만 사용하는 간단한 클라이언트입니다."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = normalize_webui_url(base_url)
        
        # 순수 호스트 주소(base_host)를 추출합니다.
        host = self.base_url
        for suffix in ("/api/v1", "/api"):
            if host.endswith(suffix):
                host = host[:-len(suffix)]
                break
        host = host.rstrip("/")
        
        # 내부 통신 시 사용할 정확한 API 엔드포인트
        self.api_base = f"{host}/api"
        self.api_v1_base = f"{host}/api/v1"
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def check_connection(self, expected_model: str) -> list:
        response = requests.get(
            f"{self.api_base}/models",
            headers=self.headers,
            timeout=REQUEST_TIMEOUT,
        )
        if not response.ok:
            raise response_error(response, "Open WebUI 연결")

        data = response.json()
        models = data.get("data", data if isinstance(data, list) else [])
        model_ids = {
            item.get("id")
            for item in models
            if isinstance(item, dict) and item.get("id")
        }
        return sorted(list(model_ids))

    def list_files(self, page: int = 1) -> dict:
        response = requests.get(
            f"{self.api_v1_base}/files/",
            params={"page": page, "content": "false"},
            headers=self.headers,
            timeout=REQUEST_TIMEOUT,
        )
        if not response.ok:
            raise response_error(response, f"파일 목록 조회 (페이지 {page})")
        try:
            return response.json()
        except ValueError as e:
            raise RuntimeError(f"파일 목록 응답 파싱 실패 (JSON 형식 아님): {e}\n응답 본문: {response.text[:200]}")

    def delete_file(self, file_id: str) -> None:
        quoted_id = quote(file_id, safe='')
        response = requests.delete(
            f"{self.api_v1_base}/files/{quoted_id}",
            headers=self.headers,
            timeout=REQUEST_TIMEOUT,
        )
        if not response.ok:
            raise response_error(response, "파일 삭제")

    def upload_pdf(self, pdf_path: Path) -> str:
        with pdf_path.open("rb") as pdf_file:
            response = requests.post(
                f"{self.api_v1_base}/files/",
                headers={**self.headers, "Accept": "application/json"},
                params={"process": "true", "process_in_background": "true"},
                files={"file": (pdf_path.name, pdf_file, "application/pdf")},
                timeout=REQUEST_TIMEOUT,
            )
        if not response.ok:
            raise response_error(response, "PDF 업로드")

        file_id = response.json().get("id")
        if not file_id:
            raise RuntimeError(f"PDF 업로드 응답에 파일 ID가 없습니다.\n{response.text}")
        return file_id

    def wait_until_processed(self, file_id: str, progress_callback) -> None:
        deadline = time.monotonic() + PROCESS_TIMEOUT
        while time.monotonic() < deadline:
            response = requests.get(
                f"{self.api_v1_base}/files/{file_id}/process/status",
                headers=self.headers,
                timeout=REQUEST_TIMEOUT,
            )
            if not response.ok:
                raise response_error(response, "PDF 처리 상태 확인")

            result = response.json()
            status = result.get("status")
            if status == "completed":
                return
            if status == "failed":
                raise RuntimeError(f"Open WebUI PDF 처리 실패\n{result.get('error', result)}")

            progress_callback(status or "pending")
            time.sleep(2)

        raise TimeoutError(
            f"PDF 처리가 {PROCESS_TIMEOUT}초 안에 완료되지 않았습니다. "
            "Open WebUI의 문서 처리 로그를 확인해 주세요."
        )

    def stream_chat(self, model: str, question: str, file_id: str):
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "첨부한 PDF를 근거로 한국어로 답하세요. 문서에 없는 내용은 "
                        "추측하지 말고 찾을 수 없다고 답하세요. 가능한 경우 근거 페이지를 표시하세요."
                    ),
                },
                {"role": "user", "content": question},
            ],
            "files": [{"type": "file", "id": file_id}],
            "stream": True,
            "temperature": 0.1,
        }

        with requests.post(
            f"{self.api_base}/chat/completions",
            headers={**self.headers, "Content-Type": "application/json"},
            json=payload,
            stream=True,
            timeout=(30, REQUEST_TIMEOUT),
        ) as response:
            if not response.ok:
                raise response_error(response, "RAG 답변 생성")

            for raw_line in response.iter_lines(decode_unicode=True):
                if not raw_line or not raw_line.startswith("data:"):
                    continue
                data_text = raw_line[5:].strip()
                if data_text == "[DONE]":
                    break
                try:
                    event = json.loads(data_text)
                except json.JSONDecodeError:
                    continue

                choices = event.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                content = delta.get("content")
                if isinstance(content, str) and content:
                    yield content


class RAGApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1050x760")
        self.root.configure(bg=BG)

        self.events = queue.Queue()
        self.client = None
        self.file_id = None
        self.model = DEFAULT_MODEL

        self._create_styles()
        self._create_widgets()
        self.root.after(100, self._process_events)

    def _create_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=PANEL, foreground=TEXT, font=(FONT, 10))
        style.configure("Title.TLabel", font=(FONT, 15, "bold"))
        style.configure("Status.TLabel", background=BG, foreground=MUTED)
        style.configure("TButton", font=(FONT, 10, "bold"), background=BLUE, foreground=WHITE)

    def _create_widgets(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        outer = ttk.Frame(self.root, padding=14)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)

        settings = ttk.Frame(outer, style="Panel.TFrame", padding=16)
        settings.grid(row=0, column=0, sticky="ns", padx=(0, 12))
        settings.columnconfigure(0, weight=1)

        # 타이틀 및 우상단 수정일 날짜 표시
        today_str = datetime.now().strftime("%Y-%m-%d")
        ttk.Label(settings, text="RAG 연결 설정", style="Title.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 14)
        )
        ttk.Label(settings, text=f"수정일: {today_str}", font=(FONT, 9), foreground=MUTED).grid(
            row=0, column=1, sticky="e", pady=(0, 14)
        )

        self.pdf_entry = self._entry_row(settings, 1, "PDF 파일")
        ttk.Button(settings, text="찾기", command=self._select_pdf).grid(row=2, column=1, padx=(6, 0))

        self.url_entry = self._entry_row(settings, 3, "Open WebUI 주소")
        self.key_entry = self._entry_row(settings, 5, "Open WebUI API Key", show="*")
        
        # 서버 연결 및 모델 조회 버튼 신설
        self.check_button = ttk.Button(settings, text="연결 확인 및 모델 조회", command=self._start_check_models)
        self.check_button.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(8, 4), ipady=3)
        
        # 답변 모델 선택 Combobox (사용자 직접 타이핑 입력도 가능)
        ttk.Label(settings, text="답변 모델").grid(row=8, column=0, columnspan=2, sticky="w", pady=(7, 2))
        self.model_entry = ttk.Combobox(settings, width=36, font=(FONT, 9))
        self.model_entry.grid(row=9, column=0, columnspan=2, sticky="ew", ipady=3)
        
        # Combobox용 placeholder 구현 ("모델명 입력" 회색 노출)
        self.model_entry.is_placeholder = True
        self.model_entry.set("모델명 입력")
        self.model_entry.config(foreground="#9CA3AF")
        
        def on_combo_focus_in(event):
            if getattr(self.model_entry, "is_placeholder", False):
                self.model_entry.set("")
                self.model_entry.config(foreground=TEXT)
                self.model_entry.is_placeholder = False
                
        def on_combo_focus_out(event):
            if self.model_entry.get().strip() == "":
                self.model_entry.set("모델명 입력")
                self.model_entry.config(foreground="#9CA3AF")
                self.model_entry.is_placeholder = True
                
        def on_combo_selected(event):
            self.model_entry.config(foreground=TEXT)
            self.model_entry.is_placeholder = False
            
        self.model_entry.bind("<FocusIn>", on_combo_focus_in)
        self.model_entry.bind("<FocusOut>", on_combo_focus_out)
        self.model_entry.bind("<<ComboboxSelected>>", on_combo_selected)
        
        # get() 오버라이드
        def get_model():
            if getattr(self.model_entry, "is_placeholder", False):
                return ""
            return ttk.Combobox.get(self.model_entry)
        self.model_entry.get = get_model

        self.load_button = ttk.Button(settings, text="PDF 업로드 및 RAG 준비", command=self._start_load)
        self.load_button.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(18, 0), ipady=7)

        info = (
            "임베딩은 Open WebUI의 RAG 설정에 등록된\n"
            "qwen3-embedding-0.6b를 사용합니다."
        )
        ttk.Label(settings, text=info, foreground=MUTED).grid(
            row=11, column=0, columnspan=2, sticky="w", pady=(12, 0)
        )

        # 서버 파일 관리 영역 (openwebui_file_cleaner.pyw 참조하여 재구성)
        ttk.Label(settings, text="서버 파일 관리", font=(FONT, 11, "bold")).grid(
            row=12, column=0, columnspan=2, sticky="w", pady=(18, 4)
        )
        
        tree_frame = ttk.Frame(settings)
        tree_frame.grid(row=13, column=0, columnspan=2, sticky="ew")
        tree_frame.columnconfigure(0, weight=1)
        
        columns = ("name", "type", "size", "created", "id")
        self.files_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=5, selectmode="extended")
        headings = {"name": "파일명", "type": "형식", "size": "크기", "created": "생성일", "id": "파일 ID"}
        widths = {"name": 140, "type": 80, "size": 65, "created": 110, "id": 110}
        
        for col in columns:
            self.files_tree.heading(col, text=headings[col])
            self.files_tree.column(col, width=widths[col], anchor="w")
            
        self.files_tree.grid(row=0, column=0, sticky="ew")
        
        v_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.files_tree.yview)
        v_scroll.grid(row=0, column=1, sticky="ns")
        self.files_tree.configure(yscrollcommand=v_scroll.set)
        
        btn_frame = ttk.Frame(settings)
        btn_frame.grid(row=14, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)
        
        self.btn_refresh = ttk.Button(btn_frame, text="목록 새로고침", command=self._start_refresh_files)
        self.btn_refresh.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        
        self.btn_delete_file = ttk.Button(btn_frame, text="선택 삭제", command=self._start_delete_files)
        self.btn_delete_file.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        chat_frame = ttk.Frame(outer)
        chat_frame.grid(row=0, column=1, sticky="nsew")
        chat_frame.columnconfigure(0, weight=1)
        chat_frame.rowconfigure(0, weight=1)

        self.chat = ScrolledText(chat_frame, wrap=tk.WORD, font=(FONT, 11), bg=WHITE, fg=TEXT)
        self.chat.grid(row=0, column=0, columnspan=2, sticky="nsew")
        self.chat.tag_configure("user", foreground=BLUE, font=(FONT, 11, "bold"))
        self.chat.tag_configure("error", foreground=RED)
        self.chat.config(state=tk.DISABLED)

        self.question_entry = ttk.Entry(chat_frame, font=(FONT, 11), state=tk.DISABLED)
        self.question_entry.grid(row=1, column=0, sticky="ew", pady=(10, 0), padx=(0, 8), ipady=7)
        self.question_entry.bind("<Return>", lambda _event: self._start_question())
        self.send_button = ttk.Button(chat_frame, text="질문 전송", command=self._start_question, state=tk.DISABLED)
        self.send_button.grid(row=1, column=1, sticky="ns", pady=(10, 0))

        self.status = ttk.Label(self.root, text=" PDF를 선택하고 RAG 준비를 실행하세요.", style="Status.TLabel")
        self.status.grid(row=1, column=0, sticky="ew", padx=8, pady=5)

    def _entry_row(self, parent, row, label, show=None):
        ttk.Label(parent, text=label).grid(row=row, column=0, columnspan=2, sticky="w", pady=(7, 2))
        entry = ttk.Entry(parent, width=38, show=show)
        entry.grid(row=row + 1, column=0, sticky="ew", ipady=5)
        return entry

    def _select_pdf(self):
        path = filedialog.askopenfilename(filetypes=[("PDF 파일", "*.pdf")])
        if path:
            self.pdf_entry.delete(0, tk.END)
            self.pdf_entry.insert(0, path)

    def _write(self, text, tag=None):
        self.chat.config(state=tk.NORMAL)
        self.chat.insert(tk.END, text, tag)
        self.chat.config(state=tk.DISABLED)
        self.chat.see(tk.END)

    def _set_busy(self, busy: bool):
        self.load_button.config(state=tk.DISABLED if busy else tk.NORMAL)
        ready = not busy and self.file_id is not None
        self.send_button.config(state=tk.NORMAL if ready else tk.DISABLED)
        self.question_entry.config(state=tk.NORMAL if ready else tk.DISABLED)

    def _start_check_models(self):
        base_url = self.url_entry.get().strip()
        api_key = self.key_entry.get().strip()
        if not base_url or not api_key:
            messagebox.showwarning("입력 확인", "주소와 API Key를 입력해 주세요.")
            return
        
        self.status.config(text=" Open WebUI 서버 모델 목록 조회 중...")
        self._write("\n[시스템] Open WebUI 서버 모델 조회를 시작합니다.\n")
        threading.Thread(target=self._check_models_task, args=(base_url, api_key), daemon=True).start()

    def _check_models_task(self, base_url, api_key):
        try:
            client = OpenWebUIClient(base_url, api_key)
            models = client.check_connection("")
            self.events.put(("models_loaded", models))
            self.events.put(("log", f"[시스템] 연결 성공: {len(models)}개의 모델이 발견되었습니다.\n"))
            self.events.put(("status", " 서버 연결 성공"))
        except Exception as error:
            self.events.put(("load_error", f"서버 연결 실패: {error}"))

    def _start_load(self):
        pdf_path = Path(self.pdf_entry.get().strip())
        base_url = self.url_entry.get().strip()
        api_key = self.key_entry.get().strip()
        model = self.model_entry.get().strip()

        if not pdf_path.is_file() or pdf_path.suffix.lower() != ".pdf":
            messagebox.showwarning("입력 확인", "올바른 PDF 파일을 선택해 주세요.")
            return
        if not base_url or not api_key or not model:
            messagebox.showwarning("입력 확인", "Open WebUI 주소, API Key, 모델명을 모두 입력해 주세요.")
            return

        self.file_id = None
        self.model = model
        self._set_busy(True)
        self.status.config(text=" Open WebUI 연결 확인 중...")
        self._write("\n[시스템] PDF 업로드와 분석을 시작합니다.\n")
        threading.Thread(target=self._load_task, args=(pdf_path, base_url, api_key, model), daemon=True).start()

    def _load_task(self, pdf_path, base_url, api_key, model):
        try:
            client = OpenWebUIClient(base_url, api_key)
            models = client.check_connection(model)
            self.events.put(("models_loaded", models))
            self.events.put(("status", " PDF를 Open WebUI에 업로드하는 중..."))
            file_id = client.upload_pdf(pdf_path)
            self.events.put(("log", f"[시스템] 업로드 완료: {pdf_path.name}\n"))
            client.wait_until_processed(
                file_id,
                lambda state: self.events.put(("status", f" PDF 분석 및 임베딩 중... ({state})")),
            )
            self.events.put(("ready", (client, file_id)))
        except Exception as error:
            self.events.put(("load_error", str(error)))

    def _start_question(self):
        question = self.question_entry.get().strip()
        if not question or not self.client or not self.file_id:
            return
        self.question_entry.delete(0, tk.END)
        self._set_busy(True)
        self._write(f"\n질문: {question}\n", "user")
        self._write("답변: ")
        self.status.config(text=" RAG 검색 및 답변 생성 중...")
        threading.Thread(target=self._question_task, args=(question,), daemon=True).start()

    def _question_task(self, question):
        try:
            for text in self.client.stream_chat(self.model, question, self.file_id):
                self.events.put(("chunk", text))
            self.events.put(("answer_done", None))
        except Exception as error:
            self.events.put(("answer_error", str(error)))

    def _start_refresh_files(self):
        base_url = self.url_entry.get().strip()
        api_key = self.key_entry.get().strip()
        if not base_url or not api_key:
            messagebox.showwarning("입력 확인", "주소와 API Key를 먼저 입력해 주세요.")
            return
        self.status.config(text=" 서버 파일 목록을 불러오는 중...")
        threading.Thread(target=self._refresh_files_task, args=(base_url, api_key), daemon=True).start()

    def _refresh_files_task(self, base_url, api_key):
        try:
            client = OpenWebUIClient(base_url, api_key)
            found, page = [], 1
            while True:
                data = client.list_files(page)
                if isinstance(data, list):
                    items, total = data, None
                else:
                    items = data.get("items", data.get("files", []))
                    total = data.get("total")
                if not isinstance(items, list):
                    raise RuntimeError("Open WebUI가 예상하지 못한 파일 목록 형식을 반환했습니다.")
                found.extend(items)
                if not items or len(items) < PAGE_SIZE or (total is not None and len(found) >= int(total)):
                    break
                page += 1
                if page > 1000:
                    raise RuntimeError("페이지 수가 비정상적으로 많아 조회를 중단했습니다.")
            self.events.put(("files_loaded", found))
        except Exception as error:
            self.events.put(("file_action_error", f"파일 목록 로드 실패: {error}"))

    def _start_delete_files(self):
        selected_items = self.files_tree.selection()
        if not selected_items:
            messagebox.showwarning("선택 확인", "삭제할 파일을 목록에서 선택해 주세요.")
            return
        
        # 파일명 모으기
        names = []
        for iid in selected_items:
            values = self.files_tree.item(iid, "values")
            if values:
                names.append(values[0])
                
        preview = "\n".join(f"• {name}" for name in names[:8])
        if len(names) > 8:
            preview += f"\n• 외 {len(names) - 8}개"
            
        if not messagebox.askyesno(
            "영구 삭제 확인",
            f"선택한 {len(names)}개 파일과 관련 임베딩을 서버에서 영구 삭제합니다.\n\n{preview}\n\n계속할까요?",
            icon="warning"
        ):
            return
            
        base_url = self.url_entry.get().strip()
        api_key = self.key_entry.get().strip()
        
        self.status.config(text=" 파일 삭제 중...")
        threading.Thread(
            target=self._delete_files_task, 
            args=(base_url, api_key, list(selected_items), names), 
            daemon=True
        ).start()

    def _delete_files_task(self, base_url, api_key, selected_ids, names):
        try:
            client = OpenWebUIClient(base_url, api_key)
            failures = []
            for index, file_id in enumerate(selected_ids, 1):
                try:
                    client.delete_file(file_id)
                except Exception as exc:
                    failures.append((names[index-1], str(exc)))
                self.events.put(("status", f" 파일 삭제 중... ({index}/{len(selected_ids)} 완료)"))
            
            self.events.put(("files_deleted", (len(selected_ids), failures)))
        except Exception as error:
            self.events.put(("file_action_error", f"삭제 중 서버 연결 실패: {error}"))

    def _process_events(self):
        while not self.events.empty():
            event, data = self.events.get()
            if event == "status":
                self.status.config(text=data)
            elif event == "log":
                self._write(data)
            elif event == "ready":
                self.client, self.file_id = data
                self._set_busy(False)
                self.status.config(text=" RAG 준비 완료")
                self._write("[시스템] PDF 분석과 임베딩이 완료되었습니다. 질문할 수 있습니다.\n")
                self.question_entry.focus_set()
                self._start_refresh_files()
            elif event == "chunk":
                self._write(data)
            elif event == "answer_done":
                self._write("\n")
                self._set_busy(False)
                self.status.config(text=" RAG 준비 완료")
                self.question_entry.focus_set()
            elif event in ("load_error", "answer_error"):
                self._write(f"\n[오류] {data}\n", "error")
                self._set_busy(False)
                self.status.config(text=" 오류 발생")
                messagebox.showerror("오류", data)
            elif event == "models_loaded":
                self.model_entry.config(values=data)
            elif event == "files_loaded":
                self.status.config(text=" RAG 준비 완료" if self.file_id else " PDF를 선택하고 RAG 준비를 실행하세요.")
                for item in self.files_tree.get_children():
                    self.files_tree.delete(item)
                
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    meta = item.get("meta") or {}
                    name = meta.get("name") or item.get("filename") or item.get("name") or "(이름 없음)"
                    kind = meta.get("content_type") or item.get("content_type") or "-"
                    size = meta.get("size", item.get("size"))
                    created = item.get("created_at", meta.get("created_at"))
                    
                    fid = str(item.get("id", ""))
                    self.files_tree.insert(
                        "", 
                        tk.END, 
                        iid=fid, 
                        values=(name, kind, human_size(size), human_date(created), fid)
                    )
            elif event == "files_deleted":
                total_count, failures = data
                success_count = total_count - len(failures)
                if failures:
                    detail = "\n".join(f"• {fname}: {msg}" for fname, msg in failures[:10])
                    if len(failures) > 10:
                        detail += f"\n외 {len(failures) - 10}개 실패"
                    messagebox.showwarning(
                        "일부 삭제 실패", 
                        f"선택한 {total_count}개 파일 중 {success_count}개 삭제 성공, {len(failures)}개 실패\n\n[실패 사유]\n{detail}"
                    )
                else:
                    messagebox.showinfo("완료", f"선택한 {success_count}개 파일을 삭제했습니다.")
                
                self._start_refresh_files()
            elif event == "file_action_error":
                self.status.config(text=" 오류 발생")
                messagebox.showerror("서버 파일 관리 오류", data)

        self.root.after(100, self._process_events)


def main():
    root = tk.Tk()
    RAGApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
