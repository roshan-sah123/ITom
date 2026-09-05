import os
import sys
sys.path.insert(0, os.path.abspath("."))
from app.core.config import Settings

wildcards = [
    "*",
    " * ",
    '"*"',
    "'*'",
    "['*']",
    "[' * ']",
    '["*"]',
    "http://localhost:8080, *",
    'http://localhost:8080, "*"',
    "['http://localhost:8080', '*']",
    ["*"],
    [" * "],
    ["http://localhost:8080", "*"],
]

for wc in wildcards:
    try:
        s = Settings(CORS_ORIGINS=wc, CORS_ALLOW_CREDENTIALS=True)
        print(f"FAILED: Permutation {wc!r} was accepted without ValueError!")
        exit(1)
    except ValueError as e:
        print(f"PASS: {wc!r} properly rejected")

# Test BACKEND_CORS_ORIGINS direct kwarg
try:
    s = Settings(BACKEND_CORS_ORIGINS=["*"], CORS_ALLOW_CREDENTIALS=True)
    print("FAILED: BACKEND_CORS_ORIGINS=['*'] was accepted!")
    exit(1)
except ValueError:
    print("PASS: BACKEND_CORS_ORIGINS=['*'] properly rejected")

# Test cross-param bypass attempt
try:
    s = Settings(BACKEND_CORS_ORIGINS=["http://localhost:8080"], CORS_ORIGINS="*", CORS_ALLOW_CREDENTIALS=True)
    print("FAILED: Cross-param bypass attempt was accepted!")
    exit(1)
except ValueError:
    print("PASS: Cross-param bypass attempt properly rejected")

# Safe when credentials disabled
s_safe = Settings(CORS_ORIGINS="*", CORS_ALLOW_CREDENTIALS=False)
assert s_safe.BACKEND_CORS_ORIGINS == ["*"]
print("PASS: wildcard accepted when allow_credentials=False:", s_safe.BACKEND_CORS_ORIGINS)

# Default origins
s_default = Settings()
assert s_default.BACKEND_CORS_ORIGINS == ["http://localhost:8080"]
assert s_default.CORS_ALLOW_CREDENTIALS is True
print("PASS: default CORS_ORIGINS:", s_default.BACKEND_CORS_ORIGINS)

print("ALL CORS FORENSIC TESTS PASSED!")
