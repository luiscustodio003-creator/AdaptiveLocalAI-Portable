from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import json, os, platform, shutil, socket, subprocess, threading, time
import urllib.error, urllib.parse, urllib.request
from calibration import Calibrator, CalibrationError, Interrupted
from model_watcher import ModelDirectoryWatcher
from model_eligibility import build_recommendations, normalize_task
from hf_discovery import discover_text_gguf_candidates
from context_manager import adaptive_chat

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "src" / "ui"
MODELS = ROOT / "models"
HOST = "127.0.0.1"
PORT = int(os.environ.get("ADAPTIVE_UI_PORT", "8080"))
LLAMA_PORT = int(os.environ.get("LLAMA_PORT", "8089"))
CTX = 2048
THREADS = max(1, min(4, (os.cpu_count() or 4) // 2))
SYSTEM_PROMPT = (
    "Responde sempre em português de Portugal, de forma clara e concisa. "
    "Quando forneceres código, usa blocos Markdown com a linguagem identificada e preserva a indentação. "
    "Inclui fora do bloco uma explicação breve da finalidade do código e das funções principais, salvo se o utilizador pedir apenas código. "
    "Não mistures explicações dentro do bloco de código; usa comentários no código apenas quando forem úteis. "
    "Quando pedirem código completo, não omitas partes com reticências. "
)

state = {"proc": None, "model": None, "loading": False, "error": None, "threads": THREADS}
lock = threading.Lock()
# CALIBRATION_INTEGRATION_V1
activity = {"active_chats": 0, "active_loads": 0}
activity_lock = threading.Lock()
maintenance = {"active": False, "model": None}


def discover_models():
    found = []
    if not MODELS.is_dir():
        return found

    files = list(MODELS.glob("*.gguf"))
    mmprojs = [p for p in files if p.name.lower().startswith("mmproj")]

    for p in sorted(files):
        if p.name.lower().startswith("mmproj"):
            continue

        is_vision = "qwen3vl" in p.name.lower()
        dependency = None
        if is_vision:
            matches = [m for m in mmprojs if "qwen3vl" in m.name.lower()]
            if matches:
                dependency = matches[0].name

        size = p.stat().st_size
        found.append({
            "name": p.name,
            "size_bytes": size,
            "size_gb": round(size / 1024 ** 3, 2),
            "multimodal": is_vision,
            "category": "vision" if is_vision else "text",
            "dependency": dependency,
            "dependency_installed": bool(dependency),
            "status": "installed",
            "actions": {"load": True, "download": False, "delete": False}
        })
    return found

def find_runtime():
    base = ROOT / "runtime"
    if base.is_dir():
        for exe in sorted(base.rglob("llama-server.exe")):
            return exe
    return None


def find_bench():
    server_exe = find_runtime()
    if server_exe is None:
        return None
    bench_name = "llama-bench.exe" if os.name == "nt" else "llama-bench"
    bench = server_exe.parent / bench_name
    return bench if bench.is_file() else None


def ram_info():
    try:
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                        ("total", ctypes.c_ulonglong), ("avail", ctypes.c_ulonglong),
                        ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong),
                        ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong),
                        ("ae", ctypes.c_ulonglong)]
        m = MS()
        m.length = ctypes.sizeof(m)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return {"total_gb": round(m.total / 1024 ** 3, 1), "available_gb": round(m.avail / 1024 ** 3, 1)}
    except Exception:
        return None


def system_status():
    drive = Path(ROOT.anchor or "/")
    try:
        disk = round(shutil.disk_usage(drive).free / 1024 ** 3)
    except Exception:
        disk = None
    threads = os.cpu_count() or 0
    os_name = platform.system()
    if os_name == "Windows":
        os_name = "Windows " + ("11" if int(platform.version().split(".")[-1] or 0) >= 22000 else platform.release())
    rt = find_runtime()
    return {
        "os": os_name,
        "cpu_cores": max(1, threads // 2), "cpu_threads": threads,
        "ram": ram_info(),
        "disk_free_gb": disk, "disk_label": (drive.drive or str(drive)),
        "gpu": "Não detetada (CPU mode)",
        "python": platform.python_version(),
        "runtime_found": rt is not None,
        "runtime_path": str(rt.relative_to(ROOT)) if rt else None,
        "server": {"model": state["model"], "loading": state["loading"],
                   "ready": server_ready(), "error": state["error"], "port": LLAMA_PORT},
        "config": {"threads": state.get("threads", THREADS), "context": CTX, "gpu_layers": 0,
                   "kv_cache_gb": round(CTX * 0.00058, 1)},
        "calibration": calibrator.status(),
    }


def server_ready():
    """Require the managed process, health endpoint, and expected model identity."""
    p = state.get("proc")
    expected = Path(state.get("model") or "").name.lower()
    if not p or p.poll() is not None or not expected:
        return False
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{LLAMA_PORT}/health", timeout=1) as response:
            if response.status != 200:
                return False
        with urllib.request.urlopen(f"http://127.0.0.1:{LLAMA_PORT}/v1/models", timeout=1) as response:
            payload = json.loads(response.read().decode("utf-8"))
        rows = payload.get("data", []) if isinstance(payload, dict) else []
        ids = [Path(str(row.get("id", ""))).name.lower() for row in rows if isinstance(row, dict)]
        return expected in ids
    except Exception:
        return False


def stop_server():
    p = state["proc"]
    if p and p.poll() is None:
        p.terminate()
        try:
            p.wait(timeout=5)
        except Exception:
            p.kill()
    state["proc"] = None
    state["model"] = None


def load_model(name, threads_override=None):
    path = MODELS / Path(name).name
    rt = find_runtime()
    if not path.is_file():
        return False, "Modelo não encontrado."
    if not rt:
        return False, "llama-server.exe não encontrado na pasta runtime."
    effective_threads = THREADS
    if threads_override is not None:
        try:
            requested_threads = int(threads_override)
        except (TypeError, ValueError):
            return False, "Numero de threads interno invalido."
        if not 1 <= requested_threads <= max(1, os.cpu_count() or 1):
            return False, "Numero de threads interno fora dos limites do CPU."
        effective_threads = requested_threads
    else:
        profile = calibrator.profile(path.name)
        if profile:
            try:
                prof_threads = int(profile.get("threads", THREADS))
                if 1 <= prof_threads <= max(1, os.cpu_count() or 1):
                    effective_threads = prof_threads
            except (TypeError, ValueError):
                pass

    with lock:
        state.update(loading=True, error=None, threads=effective_threads)
        stop_server()
        # Do not mistake an unrelated/stale listener for the process just launched.
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind((HOST, LLAMA_PORT))
        except OSError:
            state.update(loading=False, error=f"A porta {LLAMA_PORT} ja esta ocupada por outro processo.")
            return False, state["error"]
        cmd = [str(rt), "-m", str(path), "--host", HOST, "--port", str(LLAMA_PORT),
               "-c", str(CTX), "-t", str(effective_threads), "-ngl", "0"]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            state["proc"] = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                             stderr=subprocess.DEVNULL, creationflags=flags)
        except Exception as exc:
            state.update(loading=False, error=str(exc))
            return False, str(exc)
        state["model"] = path.name
        for _ in range(240):
            if state["proc"].poll() is not None:
                break
            if server_ready():
                state["loading"] = False
                return True, None
            time.sleep(0.5)
        state.update(loading=False, error="O llama-server não arrancou a tempo.")
        stop_server()
        return False, state["error"]


def chat(messages, max_tokens=512, timeout=600):
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + messages[-12:]
    body = json.dumps({"messages": msgs, "max_tokens": max(1, min(int(max_tokens), 512)), "temperature": 0.7}).encode("utf-8")
    req = urllib.request.Request(f"http://127.0.0.1:{LLAMA_PORT}/v1/chat/completions",
                                 data=body, headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    secs = max(time.monotonic() - t0, 0.001)
    toks = int(data.get("usage", {}).get("completion_tokens", 0) or 0)
    content = str(data["choices"][0]["message"]["content"]).strip()
    if toks <= 0:
        toks = max(1, round(len(content) / 3.5))
        estimated = True
    else:
        estimated = False
    return {"content": content, "seconds": round(secs, 1), "tokens": toks,
            "tok_s": round(toks / secs, 1), "tokens_estimated": estimated}


def chat_stream(messages, max_tokens=512, timeout=600, on_delta=None):
    """Stream output from llama.cpp; fall back to normal chat if streaming is unsupported."""
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + messages[-12:]
    body = json.dumps({
        "messages": msgs,
        "max_tokens": max(1, min(int(max_tokens), 512)),
        "temperature": 0.7,
        "stream": True,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{LLAMA_PORT}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    )
    t0 = time.monotonic()
    content_parts = []
    completion_tokens = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                payload_text = line[5:].strip()
                if payload_text == "[DONE]":
                    break
                try:
                    payload = json.loads(payload_text)
                except json.JSONDecodeError:
                    continue
                usage = payload.get("usage") if isinstance(payload, dict) else None
                if isinstance(usage, dict) and usage.get("completion_tokens") is not None:
                    try:
                        completion_tokens = int(usage["completion_tokens"])
                    except (TypeError, ValueError):
                        pass
                choices = payload.get("choices", []) if isinstance(payload, dict) else []
                if not choices:
                    continue
                delta = choices[0].get("delta", {}) or {}
                piece = delta.get("content", "")
                if isinstance(piece, list):
                    piece = "".join(str(x.get("text", "")) for x in piece if isinstance(x, dict))
                if piece:
                    piece = str(piece)
                    content_parts.append(piece)
                    if on_delta:
                        on_delta(piece)
    except urllib.error.HTTPError as exc:
        if exc.code not in (400, 404, 405, 415, 422, 501):
            raise
        try:
            exc.read()
        except Exception:
            pass
        fallback = chat(messages, max_tokens=max_tokens, timeout=timeout)
        fallback_content = str(fallback.get("content", ""))
        if on_delta and fallback_content:
            on_delta(fallback_content)
        fallback["tokens_estimated"] = bool(fallback.get("tokens_estimated", False))
        return fallback

    elapsed = max(time.monotonic() - t0, 0.001)
    content = "".join(content_parts).strip()
    # Some older builds accept stream=true but produce no content. Do not silently
    # return an empty answer; retry through the legacy non-streaming endpoint.
    if not content:
        fallback = chat(messages, max_tokens=max_tokens, timeout=timeout)
        fallback_content = str(fallback.get("content", ""))
        if on_delta and fallback_content:
            on_delta(fallback_content)
        return fallback
    estimated = completion_tokens is None or completion_tokens <= 0
    tokens = completion_tokens if not estimated else max(1, round(len(content) / 3.5))
    return {"content": content, "seconds": round(elapsed, 1), "tokens": int(tokens),
            "tok_s": round(float(tokens) / elapsed, 1), "tokens_estimated": estimated}

def calibration_idle():
    if state.get("loading", False):
        return False
    with activity_lock:
        return activity.get("active_chats", 0) == 0 and activity.get("active_loads", 0) == 0 and not maintenance.get("active", False)


def validate_calibrated_model(model_name, threads, cancel_event, must_abort):
    """Switch to the candidate model safely, run three real chats, then restore prior state."""
    # Reserve the app atomically once all public chat/load requests are idle.
    while True:
        if cancel_event.is_set():
            raise Interrupted("Calibracao cancelada antes da reserva da aplicacao.")
        if must_abort():
            raise CalibrationError("RAM abaixo do limite de emergencia antes da reserva da aplicacao.")
        with activity_lock:
            if (activity.get("active_chats", 0) == 0 and
                    activity.get("active_loads", 0) == 0 and
                    not maintenance.get("active", False) and
                    not state.get("loading", False)):
                maintenance.update(active=True, model=model_name)
                break
        time.sleep(0.2)

    previous_model = None
    previous_threads = int(state.get("threads", THREADS) or THREADS)
    previous_ready = False
    already_correct = False
    try:
        previous_ready = server_ready()
        if previous_ready:
            previous_model = state.get("model")
        if cancel_event.is_set():
            raise Interrupted("Calibracao cancelada antes de carregar o modelo para validacao.")
        if must_abort():
            raise CalibrationError("RAM abaixo do limite de emergencia antes da validacao.")

        already_correct = previous_ready and previous_model == model_name and previous_threads == int(threads)
        if not already_correct:
            ok, error = load_model(model_name, threads_override=threads)
            if not ok:
                raise CalibrationError(f"Nao foi possivel carregar o modelo candidato para validacao: {error}")

        prompts = [
            "Explica em portugues de Portugal, em cerca de 100 palavras, porque um programa deve medir o desempenho de um modelo local antes de escolher as threads.",
            "Descreve em portugues de Portugal, em cerca de 100 palavras, como a memoria RAM e o numero de threads podem afetar a inferencia local. Nao uses listas.",
            "Explica em portugues de Portugal, em cerca de 100 palavras, porque tres testes repetidos sao melhores do que uma unica medicao de velocidade. Nao uses listas.",
        ]
        runs = []
        for index, prompt in enumerate(prompts, start=1):
            if cancel_event.is_set():
                raise Interrupted("Calibracao cancelada durante os testes de inferencia.")
            if must_abort():
                raise CalibrationError("RAM abaixo do limite de emergencia durante a validacao.")
            response = chat([{"role": "user", "content": prompt}], max_tokens=180, timeout=90)
            content = str(response.get("content", "")).strip()
            tokens = int(response.get("tokens", 0) or 0)
            speed = float(response.get("tok_s", 0) or 0)
            if not content or tokens <= 0 or speed <= 0:
                raise CalibrationError(f"Teste de inferencia {index} nao produziu uma resposta/medicao valida.")
            runs.append({
                "test": index,
                "seconds": float(response.get("seconds", 0) or 0),
                "tokens": tokens,
                "tok_s": round(speed, 4),
                "response_chars": len(content),
            })

        rates = sorted(item["tok_s"] for item in runs)
        median_rate = rates[len(rates) // 2]
        validation = {
            "status": "passed", "passed": True, "tests": len(runs),
            "median_tok_s": round(median_rate, 4),
            "min_tok_s": round(min(rates), 4), "max_tok_s": round(max(rates), 4),
            "runs": runs, "tested_threads": int(threads),
        }
    except Exception as exc:
        validation_error = exc
        validation = None
    else:
        validation_error = None
    finally:
        restore_error = None
        try:
            if previous_model and not already_correct:
                ok, error = load_model(previous_model, threads_override=previous_threads)
                if not ok:
                    raise CalibrationError(f"Validacao terminou mas nao foi possivel restaurar {previous_model}: {error}")
            else:
                with lock:
                    stop_server()
                    state.update(loading=False, error=None, threads=THREADS)
        except Exception as exc:
            restore_error = exc
        with activity_lock:
            maintenance.update(active=False, model=None)

    if restore_error is not None:
        raise CalibrationError(f"Falha ao restaurar o estado anterior apos a validacao: {restore_error}") from restore_error
    if validation_error is not None:
        if isinstance(validation_error, CalibrationError):
            raise validation_error
        raise CalibrationError(f"Validacao de inferencia falhou: {validation_error}") from validation_error
    return validation


calibrator = Calibrator(ROOT, find_bench, calibration_idle, validator=validate_calibrated_model)
model_watcher = ModelDirectoryWatcher(ROOT, calibrator)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(UI), **k)

    def log_message(self, fmt, *args):
        print("[HTTP] " + (fmt % args))

    def send_json(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/status":
            self.send_json(system_status())
        elif path == "/api/models":
            self.send_json({"models": discover_models()})
        elif path == "/api/catalog":
            self.send_json({
                "catalog": discover_models(),
                "categories": [
                    {"id": "all", "label": "Todos"},
                    {"id": "text", "label": "Texto"},
                    {"id": "vision", "label": "Visão"}
                ],
                "remote_downloads": False,
                "deletion_enabled": False
            })
        elif path == "/api/recommendations":
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            requested_task = query.get("task", ["text"])[0]
            try:
                task = normalize_task(requested_task)
            except ValueError as exc:
                return self.send_json({"ok": False, "error": str(exc)}, 400)
            system = system_status()
            ram = system.get("ram") or {}
            hardware = {
                "total_ram_gb": ram.get("total_gb"),
                "available_ram_gb": ram.get("available_gb"),
                "cpu_threads": system.get("cpu_threads", os.cpu_count() or 1),
                "disk_free_gb": system.get("disk_free_gb"),
                "context": CTX,
                "active_model": state.get("model") if system.get("server", {}).get("ready") else None,
            }
            installed = discover_models()
            profiles = {}
            for model_item in installed:
                saved_profile = calibrator.profile(model_item["name"], include_stale=True)
                if saved_profile is not None:
                    profiles[model_item["name"]] = saved_profile
            runtimes = {
                "llama.cpp": bool(system.get("runtime_found")),
                # audio.cpp is deliberately unavailable until a dedicated adapter/pipeline is integrated.
                "audio.cpp_integrated": False,
            }
            discovery = {
                "state": "not_applicable", "source": "Hugging Face Hub API",
                "cached": False, "repositories_checked": 0,
                "candidates_found": 0, "error": None,
                "ranking": "Hardware/runtime filtering precedes final ranking.",
            }
            remote_candidates = []
            if task == "text":
                force_refresh = query.get("refresh", ["0"])[0] == "1"
                discovery = discover_text_gguf_candidates(
                    total_ram_gb=hardware.get("total_ram_gb"),
                    available_ram_gb=hardware.get("available_ram_gb"),
                    disk_free_gb=hardware.get("disk_free_gb"),
                    context=hardware.get("context", CTX),
                    force_refresh=force_refresh,
                )
                remote_candidates = discovery.pop("candidates", [])
            payload = build_recommendations(
                ROOT, task, installed, hardware, profiles, runtimes,
                remote_candidates=remote_candidates,
            )
            payload["discovery"] = discovery
            if task == "text" and discovery.get("state") != "ready":
                payload["message"] += " A descoberta dinâmica do Hub esta temporariamente indisponivel; os candidatos curados continuam disponiveis."
            elif task == "text":
                payload["message"] += " Descoberta dinâmica: {} candidatos compatíveis encontrados; a ordenacao final privilegia recursos e tamanho, nao downloads.".format(discovery.get("candidates_found", 0))
            return self.send_json(payload)
        elif path == "/api/hub":
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            search = (query.get("q", [""])[0] or "").strip()[:100]
            try:
                limit = int(query.get("limit", ["20"])[0])
            except ValueError:
                limit = 20
            limit = max(1, min(limit, 30))
            params = {
                "filter": "gguf",
                "sort": "downloads",
                "direction": "-1",
                "limit": str(limit)
            }
            if search:
                params["search"] = search
            url = "https://huggingface.co/api/models?" + urllib.parse.urlencode(params)
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "AdaptiveLocalAI-Portable/1.0"}
            )
            try:
                with urllib.request.urlopen(request, timeout=8) as response:
                    items = json.loads(response.read().decode("utf-8"))
                models = []
                for item in items:
                    model_id = item.get("id", "")
                    tags = item.get("tags", []) or []
                    models.append({
                        "id": model_id,
                        "downloads": item.get("downloads", 0),
                        "likes": item.get("likes", 0),
                        "pipeline_tag": item.get("pipeline_tag"),
                        "tags": tags[:20],
                        "source": "Hugging Face",
                        "installed": any(
                            model_id.lower() in str(m.get("name", "")).lower()
                            for m in discover_models()
                        )
                    })
                self.send_json({
                    "ok": True,
                    "source": "Hugging Face",
                    "count": len(models),
                    "models": models,
                    "downloads_enabled": False
                })
            except Exception as exc:
                self.send_json({
                    "ok": False,
                    "source": "Hugging Face",
                    "error": str(exc)[:300],
                    "models": [],
                    "downloads_enabled": False
                }, 502)
        elif path == "/api/calibration":
            profiles = {}
            for item in discover_models():
                profile = calibrator.profile(item["name"], include_stale=True)
                if profile is not None:
                    profiles[item["name"]] = {
                        "threads": profile.get("threads"),
                        "generation_tok_s": profile.get("generation_tok_s"),
                        "created_at": profile.get("created_at"),
                        "stale": profile.get("stale", False),
                        "validation_status": (profile.get("validation") or {}).get("status", "not_run"),
                        "validation_passed": (profile.get("validation") or {}).get("passed", False),
                        "validation_median_tok_s": (profile.get("validation") or {}).get("median_tok_s"),
                    }
            self.send_json({"ok": True, "status": calibrator.status(), "profiles": profiles,
                            "watcher": model_watcher.status()})
        elif path == "/api/health":
            self.send_json({"ok": True, "app": "AdaptiveLocalAI-Portable"})
        elif path.startswith("/api/"):
            self.send_json({"error": "Endpoint não encontrado"}, 404)
        else:
            if path == "/":
                self.path = "/index.html"
            super().do_GET()

    def handle_streaming_chat(self, body):
        """SSE endpoint that sends analysis progress and answer tokens to the browser."""
        wait_deadline = time.monotonic() + 180.0
        while True:
            with activity_lock:
                validation_active = maintenance.get("active", False)
                if not validation_active:
                    activity["active_chats"] += 1
                    break
            if time.monotonic() >= wait_deadline:
                return self.send_json({"error": "A calibração automática ainda está a decorrer; tenta novamente."}, 503)
            time.sleep(0.1)

        if not server_ready():
            with activity_lock:
                activity["active_chats"] = max(0, activity.get("active_chats", 0) - 1)
            return self.send_json({"error": "Nenhum modelo está ativo."}, 409)

        response_started = False
        def emit(event):
            payload = ("data: " + json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n\n").encode("utf-8")
            self.wfile.write(payload)
            self.wfile.flush()

        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Connection", "close")
            self.end_headers()
            response_started = True
            result = adaptive_chat(
                body.get("messages", []), call_once=chat, call_stream=chat_stream,
                emit=emit, context_tokens=CTX, system_prompt=SYSTEM_PROMPT,
            )
            public_result = {key: value for key, value in result.items() if key != "content"}
            emit({"type": "done", **public_result})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            if response_started:
                try:
                    emit({"type": "error", "error": str(exc)[:800]})
                except Exception:
                    pass
            else:
                self.send_json({"error": str(exc)}, 500)
        finally:
            with activity_lock:
                activity["active_chats"] = max(0, activity.get("active_chats", 0) - 1)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            body = self.read_body()
            if path == "/api/calibrate":
                requested_name = str(body.get("name") or "").strip()
                model_name = Path(requested_name).name
                if not model_name or not model_name.lower().endswith(".gguf"):
                    return self.send_json({"accepted": False, "error": "Indica um nome de modelo GGUF instalado."}, 400)
                if not (MODELS / model_name).is_file():
                    return self.send_json({"accepted": False, "error": "Modelo nao encontrado."}, 404)
                try:
                    result = calibrator.start(model_name)
                except CalibrationError as exc:
                    return self.send_json({"accepted": False, "error": str(exc)}, 400)
                return self.send_json(result, 202 if result.get("accepted") else 409)
            elif path == "/api/calibrate/cancel":
                result = calibrator.cancel()
                return self.send_json(result, 200 if result.get("accepted") else 409)
            elif path == "/api/model-installed":
                name = str(body.get("name") or "").strip()
                result = model_watcher.notify_model_installed(name)
                return self.send_json(result, 202 if result.get("accepted") else 409)
            elif path == "/api/load":
                with activity_lock:
                    validation_active = maintenance.get("active", False)
                    if not validation_active:
                        activity["active_loads"] += 1
                if validation_active:
                    return self.send_json({"ok": False, "error": "Carregamento temporariamente bloqueado durante a validacao da calibracao."}, 409)
                try:
                    ok, err = load_model(body.get("name", ""))
                finally:
                    with activity_lock:
                        activity["active_loads"] = max(0, activity.get("active_loads", 0) - 1)
                self.send_json({"ok": ok, "error": err}, 200 if ok else 500)
            elif path == "/api/chat/stream":
                return self.handle_streaming_chat(body)
            elif path == "/api/chat":
                wait_deadline = time.monotonic() + 180.0
                while True:
                    with activity_lock:
                        validation_active = maintenance.get("active", False)
                        if not validation_active:
                            activity["active_chats"] += 1
                            break
                    if time.monotonic() >= wait_deadline:
                        return self.send_json({"error": "A calibração automática ainda está a decorrer; tenta novamente."}, 503)
                    time.sleep(0.1)
                if not server_ready():
                    with activity_lock:
                        activity["active_chats"] = max(0, activity.get("active_chats", 0) - 1)
                    return self.send_json({"error": "Nenhum modelo está ativo."}, 409)
                try:
                    return self.send_json(adaptive_chat(
                        body.get("messages", []), call_once=chat, call_stream=chat_stream,
                        context_tokens=CTX, system_prompt=SYSTEM_PROMPT,
                    ))
                finally:
                    with activity_lock:
                        activity["active_chats"] = max(0, activity.get("active_chats", 0) - 1)
            else:
                self.send_json({"error": "Endpoint não encontrado"}, 404)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)


def main():
    if not (UI / "index.html").is_file():
        raise SystemExit(f"Interface não encontrada: {UI / 'index.html'}")
    try:
        server = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError as exc:
        raise SystemExit(f"Não foi possível abrir http://{HOST}:{PORT}/. Porta ocupada? {exc}")
    print("=" * 62)
    print(" Local AI Assistant")
    print("=" * 62)
    print(f"Projeto  : {ROOT}")
    print(f"Modelos  : {len(discover_models())}")
    print(f"Interface: http://{HOST}:{PORT}/")
    print(f"llama.cpp: porta {LLAMA_PORT}")
    print("Parar    : Ctrl+C")
    print("=" * 62)
    model_watcher.start()
    print("Auto-calibracao: a vigiar novos modelos GGUF em models/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nA terminar...")
    finally:
        model_watcher.stop()
        stop_server()
        server.server_close()


if __name__ == "__main__":
    main()
