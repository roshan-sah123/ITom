"""ITOM OPS Analytics & Microsoft Intune Integration Test Suite.

This package contains multi-tier automated test suites covering:
- Tier 1: Core Feature Coverage (Happy path & contracts)
- Tier 2: Boundary Value Analysis & Edge Cases (BVA)
- Tier 3: Cross-Feature Interactions & Combinations
- Tier 4: Real-World Enterprise Workload Scenarios
- Data Integrity: Multi-Agent Invariant Verification (25,987 Endpoints)
"""

__version__ = "1.0.0"
__author__ = "ITOM SRE & Quality Assurance Team"

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND = os.path.join(_ROOT, "backend")

if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
