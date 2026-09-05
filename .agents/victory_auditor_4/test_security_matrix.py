import os
import sys
sys.path.insert(0, os.path.abspath("."))
from app.core.config import Settings

# --- R3: SECRET_KEY tests ---
# Development allows empty/None SECRET_KEY
s_dev = Settings(ENVIRONMENT="development", SECRET_KEY="")
assert s_dev.SECRET_KEY == ""
s_dev_none = Settings(ENVIRONMENT="development", SECRET_KEY=None)
assert s_dev_none.SECRET_KEY is None

# Non-development rejects None/empty
for env in ["production", "staging"]:
    for bad_key in [None, "", "   "]:
        try:
            Settings(ENVIRONMENT=env, SECRET_KEY=bad_key, DEBUG=False)
            print(f"FAILED: Environment {env} accepted bad SECRET_KEY: {bad_key!r}")
            exit(1)
        except ValueError as e:
            pass

    # Reject short keys
    for short_key in ["123", "a" * 15]:
        try:
            Settings(ENVIRONMENT=env, SECRET_KEY=short_key, DEBUG=False)
            print(f"FAILED: Environment {env} accepted short SECRET_KEY: {short_key!r}")
            exit(1)
        except ValueError as e:
            assert "at least 16 characters long" in str(e)

    # Reject placeholders
    for ph in [
        "itom-secret-key-change-in-production-0987654321",
        "your-secret-key-here",
        "your-secret-key",
        "secret",
        "changeme",
        "password",
        "admin",
        "test",
        "dummy",
        "12345678",
        "secretkey",
        "placeholder",
    ]:
        try:
            Settings(ENVIRONMENT=env, SECRET_KEY=ph, DEBUG=False)
            print(f"FAILED: Environment {env} accepted placeholder: {ph!r}")
            exit(1)
        except ValueError as e:
            pass

    # Accepts strong key
    s_valid = Settings(ENVIRONMENT=env, SECRET_KEY="a" * 32, DEBUG=False)
    assert s_valid.SECRET_KEY == "a" * 32

print("PASS: R3 SECRET_KEY forensic validations all passed!")

# --- R4: DEBUG tests ---
# Default DEBUG must be False
s_default = Settings()
assert s_default.DEBUG is False, f"Expected default DEBUG=False, got {s_default.DEBUG}"

# DEBUG=True in production prohibited
try:
    Settings(ENVIRONMENT="production", DEBUG=True, SECRET_KEY="a" * 32)
    print("FAILED: Production accepted DEBUG=True")
    exit(1)
except ValueError as e:
    assert "DEBUG mode is strictly prohibited in production" in str(e)

# DEBUG=True in staging prohibited
try:
    Settings(ENVIRONMENT="staging", DEBUG=True, SECRET_KEY="a" * 32)
    print("FAILED: Staging accepted DEBUG=True")
    exit(1)
except ValueError as e:
    assert "DEBUG mode is only permitted in development" in str(e)

# DEBUG=True permitted in development
s_dev_dbg = Settings(ENVIRONMENT="development", DEBUG=True)
assert s_dev_dbg.DEBUG is True

print("PASS: R4 DEBUG forensic validations all passed!")

# --- Check .env.example ---
with open(".env.example", "r", encoding="utf-8") as f:
    env_content = f.read()

assert "CORS_ORIGINS=http://localhost:8080" in env_content
assert "openssl rand -hex 32" in env_content
assert "DEBUG=False" in env_content
assert "SECRET_KEY=" in env_content
print("PASS: .env.example documentation requirements all present!")
