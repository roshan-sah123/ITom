#!/usr/bin/env python3
"""Automated Deployment Engine: ITOM Portal to On-Premise Linux VM.

Deploys portal files, sets up 24/7 self-healing systemd service,
and schedules automatic telemetry sync engine on the target VM.
"""

import argparse
import os
import sys
import subprocess
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SSH_KEY_PATH = os.getenv("SSH_KEY_PATH", os.path.join(os.path.expanduser("~"), ".ssh", "id_rsa"))

def run_ssh(host, user, cmd, key_path=None):
    ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10"]
    if key_path and os.path.exists(key_path):
        ssh_cmd.extend(["-i", key_path])
    ssh_cmd.append(f"{user}@{host}")
    ssh_cmd.append(cmd)
    return subprocess.run(ssh_cmd, capture_output=True, text=True)

def main():
    parser = argparse.ArgumentParser(description="Deploy ITOM Portal to Remote VM")
    parser.add_argument("--host", default=os.getenv("LOCAL_SERVER_IP", "127.0.0.1"), help="Target VM IP")
    parser.add_argument("--user", default=os.getenv("LOCAL_SERVER_USER", "roshan"), help="SSH Username")
    parser.add_argument("--port", type=int, default=8080, help="Portal Web Port")
    args = parser.parse_args()

    print(f"[*] Connecting to Target VM {args.user}@{args.host}...")
    test_res = run_ssh(args.host, args.user, "uname -a && uptime", key_path=SSH_KEY_PATH)
    if test_res.returncode != 0:
        print(f"[!] Direct SSH connection failed.")
        print(f"STDERR: {test_res.stderr.strip()}")
        print("\nPlease ensure GlobalProtect VPN is Connected so the 172.18.51.x subnet is reachable.")
        return 1

    print(f"[+] Connected to VM: {test_res.stdout.strip()}")
    print("[*] Creating remote directory structure /home/roshan/itom-portal...")
    run_ssh(args.host, args.user, "mkdir -p /home/roshan/itom-portal/data /home/roshan/itom-portal/systemd /home/roshan/itom-portal/src /home/roshan/itom-portal/scripts", key_path=SSH_KEY_PATH)

    print("[*] Syncing portal files and self-healing configurations to VM...")
    scp_cmd = [
        "scp", "-r", "-o", "StrictHostKeyChecking=no",
        "-i", SSH_KEY_PATH if os.path.exists(SSH_KEY_PATH) else "",
        os.path.join(PROJECT_ROOT, "index.html"),
        os.path.join(PROJECT_ROOT, "ops_analytics.html"),
        os.path.join(PROJECT_ROOT, "app.js"),
        os.path.join(PROJECT_ROOT, "ops_analytics.js"),
        os.path.join(PROJECT_ROOT, "style.css"),
        os.path.join(PROJECT_ROOT, "logo.png"),
        os.path.join(PROJECT_ROOT, "data"),
        os.path.join(PROJECT_ROOT, "src"),
        os.path.join(PROJECT_ROOT, "scripts"),
        os.path.join(PROJECT_ROOT, "systemd"),
        f"{args.user}@{args.host}:/home/roshan/itom-portal/"
    ]
    scp_cmd = [c for c in scp_cmd if c]
    subprocess.run(scp_cmd, check=True)
    print("[+] Files successfully transferred to VM.")

    print("[*] Configuring and activating 24/7 self-healing systemd service on VM...")
    service_file = os.path.join(PROJECT_ROOT, "systemd", "itom.service")
    if os.path.exists(service_file):
        with open(service_file, "r", encoding="utf-8") as f:
            service_content = f.read()
    else:
        service_content = f"""[Unit]
Description=ITOM Enterprise Portal & Telemetry Auto-Sync Engine
After=network.target network-online.target systemd-networkd.service NetworkManager.service
Wants=network-online.target

[Service]
Type=simple
User={args.user}
Group={args.user}
WorkingDirectory=/home/roshan/itom-portal
ExecStart=/usr/bin/python3 /home/roshan/itom-portal/scripts/start_server.py
Restart=always
RestartSec=3
StartLimitIntervalSec=60
StartLimitBurst=10
Environment=PYTHONUNBUFFERED=1
Environment=PORT={args.port}
Environment=HOST=0.0.0.0
StandardOutput=journal+console
StandardError=journal+console
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
"""
    create_svc_cmd = (
        f"echo '{service_content}' | sudo tee /etc/systemd/system/itom.service >/dev/null && "
        f"sudo ln -sf /etc/systemd/system/itom.service /etc/systemd/system/itom-portal.service && "
        f"sudo systemctl daemon-reload && "
        f"sudo systemctl enable --now itom.service"
    )
    run_ssh(args.host, args.user, create_svc_cmd, key_path=SSH_KEY_PATH)

    print(f"\n[✓] Deployment Complete! ITOM Self-Healing Service is running 24/7 on:")
    print(f"    http://{args.host}:{args.port}/")
    print(f"    http://{args.host}:{args.port}/ops_analytics.html\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())
