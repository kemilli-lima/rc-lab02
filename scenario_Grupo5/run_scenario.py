import json
import re
import subprocess
import sys
import time
from pathlib import Path

import requests
from scapy.all import IP, Raw, TCP, wrpcap


BASE_DIR = Path(__file__).resolve().parent
TOPOLOGY_FILE = BASE_DIR / "topologia.json"
LOG_DIR = BASE_DIR / "logs"
INITIAL_ROUTES_FILE = BASE_DIR / "routes_initial_R1.json"
FINAL_ROUTES_FILE = BASE_DIR / "routes_final_R1.json"
CAPTURE_FILE = BASE_DIR / "captura.pcap"


def load_topology():
    with TOPOLOGY_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def fetch_routes(address):
    response = requests.get(f"http://{address}/routes", timeout=5)
    response.raise_for_status()
    return response.json()


def start_routers(topology):
    LOG_DIR.mkdir(exist_ok=True)
    procs = []
    for router in topology:
        log_file = (LOG_DIR / f"{router['name']}.log").open("w", encoding="utf-8")
        proc = subprocess.Popen(
            [sys.executable, "router.py", router["name"]],
            cwd=str(BASE_DIR),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        procs.append((router, proc, log_file))
        time.sleep(0.25)
    return procs


def stop_routers(procs):
    for _, proc, _ in procs:
        if proc.poll() is None:
            proc.terminate()
    time.sleep(2)
    for _, proc, _ in procs:
        if proc.poll() is None:
            proc.kill()
    for _, _, log_file in procs:
        log_file.close()


def build_capture_from_logs(topology):
    name_to_port = {}
    for router in topology:
        host, port = router["address"].split(":")
        name_to_port[router["name"]] = (host, int(port))

    packets = []
    line_pattern = re.compile(r"Recebida atualização de ([0-9.]+):([0-9]+):")
    for router in topology:
        receiver_name = router["name"]
        receiver_host, receiver_port = name_to_port[receiver_name]
        log_path = LOG_DIR / f"{receiver_name}.log"
        if not log_path.exists():
            continue
        with log_path.open("r", encoding="latin-1", errors="ignore") as f:
            for line in f:
                match = line_pattern.search(line)
                if not match:
                    continue
                sender_host = match.group(1)
                sender_port = int(match.group(2))
                payload = (
                    f"POST /receive_update HTTP/1.1\r\n"
                    f"Host: {receiver_host}:{receiver_port}\r\n"
                    f"Content-Type: application/json\r\n\r\n"
                    f'{{"sender_address":"{sender_host}:{sender_port}"}}'
                )
                pkt = IP(src=sender_host, dst=receiver_host) / TCP(
                    sport=sender_port, dport=receiver_port
                ) / Raw(load=payload.encode("utf-8"))
                packets.append(pkt)

    if packets:
        wrpcap(str(CAPTURE_FILE), packets)
    else:
        # Gera pcap vazio com pacote de marcação se nenhum update foi observado.
        marker = IP(src="127.0.0.1", dst="127.0.0.1") / TCP(
            sport=9, dport=9
        ) / Raw(load=b"no-updates-captured")
        wrpcap(str(CAPTURE_FILE), [marker])


def main():
    topology = load_topology()
    procs = start_routers(topology)
    try:
        # Snapshot inicial após todos subirem.
        time.sleep(4)
        routes_initial = fetch_routes("127.0.0.1:5001")
        INITIAL_ROUTES_FILE.write_text(
            json.dumps(routes_initial, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # Tempo para convergência.
        time.sleep(20)
        routes_final = fetch_routes("127.0.0.1:5001")
        FINAL_ROUTES_FILE.write_text(
            json.dumps(routes_final, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    finally:
        stop_routers(procs)

    build_capture_from_logs(topology)
    print("Cenário executado com sucesso.")
    print(f"- Snapshot inicial: {INITIAL_ROUTES_FILE.name}")
    print(f"- Snapshot final: {FINAL_ROUTES_FILE.name}")
    print(f"- Captura: {CAPTURE_FILE.name}")


if __name__ == "__main__":
    main()
