import os
import socket
import sys
from elh.config import load_config
from elh.web.app import create_app

app = create_app()

def _get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        # Doesn't have to be reachable, just triggers OS routing decision
        s.connect(('192.168.1.1', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "192.168.1.30"

if __name__ == "__main__":
    import uvicorn
    config = load_config()
    host = os.environ.get("ELH_WEB_HOST", config.web_host or "0.0.0.0")
    port = int(os.environ.get("ELH_WEB_PORT", config.web_port or 8080))
    local_ip = _get_local_ip()
    print(f"Starting ELH Web Frontend on http://{host}:{port} ...")
    print(f"  Local access:   http://127.0.0.1:{port}")
    if host in ("0.0.0.0", local_ip):
        print(f"  Network access: http://{local_ip}:{port}")
    reload_flag = os.environ.get("ELH_RELOAD", "1").lower() in ("1", "true", "yes")
    uvicorn.run("web_main:app", host=host, port=port, reload=reload_flag)
