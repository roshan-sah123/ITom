---
name: test-driven-development
description: Drives development with tests. Use when implementing any logic, fixing any bug, or changing any behavior. Use when you need to prove that code works, when a bug report arrives, or when you're about to modify existing functionality.
---

# Test-Driven Development (TDD) Skill

## 1. Overview & Core Philosophy
Write a failing test before writing the code that makes it pass. For bug fixes, reproduce the bug with a test before attempting a fix. Tests are empirical proof — "seems right" is not done. A codebase with good tests is an AI agent's superpower; a codebase without tests is a liability.

## 2. When to Use
- Implementing any new logic, endpoints, or data services.
- Fixing bugs (the Prove-It Pattern).
- Modifying existing backend or frontend functionality.
- Adding edge case handling and data boundary defenses.
- Refactoring models, repositories, or services.

**When NOT to use:** Pure configuration edits, documentation updates, or static visual tweaks that have zero behavioral impact.

## 3. The TDD Cycle

```text
    RED                GREEN              REFACTOR
 Write a test    Write minimal code    Clean up the
 that fails  ──→  to make it pass  ──→  implementation  ──→  (repeat)
      │                  │                    │
      ▼                  ▼                    ▼
   Test FAILS        Test PASSES         Tests still PASS
```

### Step 1: RED — Write a Failing Test
1. Identify the requirement or bug boundary.
2. Write a minimal test asserting the expected behavior.
3. Run the test to confirm it fails for the expected reason (e.g., `AssertionError`, `404`, `422`). If it passes initially, the test is invalid.

### Step 2: GREEN — Write Minimal Code
1. Implement only the logic needed to make the test pass.
2. Do not prematurely over-engineer or add extraneous features.
3. Run the test suite to confirm passing status.

### Step 3: REFACTOR — Clean & Harden
1. Improve code readability, modularity, and adherence to design patterns.
2. Remove duplication while keeping tests green.
3. Verify regression test coverage across related modules.
