"""Tests for Server Hardening, Dynamic IP Discovery, and 24/7 Resilience Configurations."""

import os
import re
import sys
import socket
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.start_server import get_dynamic_ips, CustomHTTPHandler, ThreadingHTTPServer, PORT, HOST


def test_dynamic_ip_resolution():
    """Verify that get_dynamic_ips returns valid non-loopback IPv4 addresses."""
    ips = get_dynamic_ips()
    assert isinstance(ips, list)
    assert len(ips) >= 1
    
    # Verify each IP is a valid IPv4 address
    ipv4_pattern = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
    for ip in ips:
        assert ipv4_pattern.match(ip), f"Invalid IP format: {ip}"
        octets = [int(o) for o in ip.split(".")]
        assert all(0 <= o <= 255 for o in octets), f"Octet out of range in IP: {ip}"
        # API should exclude APIPA 169.254.x.x addresses
        assert not ip.startswith("169.254."), f"APIPA link-local IP leaked: {ip}"


def test_systemd_service_file_specifications():
    """Verify systemd/itom.service adheres strictly to resilience requirements."""
    service_path = os.path.join(PROJECT_ROOT, "systemd", "itom.service")
    assert os.path.exists(service_path), "systemd/itom.service file must exist"
    
    with open(service_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Verify self-healing auto-restart configuration
    assert "Restart=always" in content, "systemd service must specify Restart=always"
    assert "RestartSec=3" in content, "systemd service must specify RestartSec=3"
    
    # Verify Unit dependencies
    assert "After=" in content and "network-online.target" in content
    assert "Wants=network-online.target" in content

    # Verify ExecStart and WorkingDirectory
    assert "ExecStart=/usr/bin/python3 /home/roshan/itom-portal/scripts/start_server.py" in content
    assert "WorkingDirectory=/home/roshan/itom-portal" in content
    assert "WantedBy=multi-user.target" in content


def test_start_itom_service_bat_content():
    """Verify the Windows entry point manages the canonical local services."""
    bat_path = os.path.join(PROJECT_ROOT, "start_itom_service.bat")
    assert os.path.exists(bat_path), "start_itom_service.bat file must exist"
    
    with open(bat_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "scripts\\local_itom_supervisor.py" in content


def test_register_startup_service_ps1_content():
    """Verify register_startup_service.ps1 contains resilient Scheduled Task configuration."""
    ps1_path = os.path.join(PROJECT_ROOT, "register_startup_service.ps1")
    assert os.path.exists(ps1_path), "register_startup_service.ps1 file must exist"
    
    with open(ps1_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Dynamic path handling
    assert "$PSScriptRoot" in content
    assert "local_itom_supervisor.py" in content
    
    # Task resilience settings
    assert "AllowStartIfOnBatteries" in content
    assert "DontStopIfGoingOnBatteries" in content
    assert "RestartCount" in content
    assert "RestartInterval" in content
    assert "ExecutionTimeLimit" in content


def test_deploy_to_vm_script_configuration():
    """Verify deploy_to_vm.py synchronizes systemd service and starts itom.service."""
    deploy_path = os.path.join(PROJECT_ROOT, "scripts", "deploy_to_vm.py")
    assert os.path.exists(deploy_path), "scripts/deploy_to_vm.py must exist"
    
    with open(deploy_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "itom.service" in content
    assert "Restart=always" in content
    assert "RestartSec=3" in content
    assert "start_server.py" in content


def test_threading_http_server_socket_options():
    """Verify ThreadingHTTPServer enables address reuse."""
    assert ThreadingHTTPServer.daemon_threads is True
    assert ThreadingHTTPServer.allow_reuse_address is True
