import os


def env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer.") from exc
    if value < minimum or value > maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}.")
    return value


port = env_int("GIZMOAPP_PORT", 8001, 1024, 65535)
bind = f"127.0.0.1:{port}"
workers = env_int("GIZMOAPP_GUNICORN_WORKERS", 2, 1, 16)
threads = env_int("GIZMOAPP_GUNICORN_THREADS", 2, 1, 32)
timeout = env_int("GIZMOAPP_GUNICORN_TIMEOUT", 60, 5, 300)
graceful_timeout = 20
worker_tmp_dir = os.getenv("GIZMOAPP_GUNICORN_WORKER_TMP_DIR", "/dev/shm")
if not os.path.isdir(worker_tmp_dir):
    worker_tmp_dir = None
control_socket_disable = True
accesslog = "-"
errorlog = "-"
capture_output = True
