"""Security validators, read-only query guards, and SWQL protection."""

import re
from typing import List, Set


class SolarWindsSecurityError(Exception):
    """Exception raised when a forbidden write/mutation operation is attempted against SolarWinds."""
    pass


ALLOWED_METHODS: List[str] = ["GET"]

FORBIDDEN_SWQL_KEYWORDS: Set[str] = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "CREATE",
    "TRUNCATE",
    "EXEC",
    "EXECUTE",
    "GRANT",
    "REVOKE",
    "MERGE",
}

# Regex pattern matching forbidden keywords as whole words
_FORBIDDEN_KEYWORDS_PATTERN = re.compile(
    r"\b(" + "|".join(FORBIDDEN_SWQL_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


def validate_swql_read_only(query_str: str) -> None:
    """Validate that a SWQL query is strictly read-only and non-mutating.

    Args:
        query_str: The SWQL query string to validate.

    Raises:
        SolarWindsSecurityError: If query contains mutating keywords, SQL comment obfuscation,
                                 or does not start with SELECT.
    """
    if not query_str or not isinstance(query_str, str):
        raise SolarWindsSecurityError("Query must be a non-empty string.")

    cleaned = query_str.strip()
    if not cleaned:
        raise SolarWindsSecurityError("Query must be a non-empty string.")

    # Check for SQL comments (disallowed or stripped for inspection)
    if cleaned.startswith("--") or cleaned.startswith("/*"):
        raise SolarWindsSecurityError(
            "SolarWinds integration is strictly READ-ONLY. SQL comments are forbidden."
        )

    # Clean leading whitespace/comments if embedded
    first_word = cleaned.split()[0].upper() if cleaned.split() else ""
    if first_word != "SELECT":
        raise SolarWindsSecurityError(
            f"SolarWinds integration is strictly READ-ONLY. Queries must start with SELECT (got: {first_word})."
        )

    # Check for forbidden keywords appearing as statements/commands
    # Tokenize by stripping string literals first to avoid false positives inside strings
    # Simple tokenization: look for standalone keywords
    # If query contains semicolon followed by statements, check every statement
    statements = [s.strip() for s in cleaned.split(";") if s.strip()]
    if len(statements) > 1:
        for stmt in statements[1:]:
            stmt_first_word = stmt.split()[0].upper() if stmt.split() else ""
            if stmt_first_word in FORBIDDEN_SWQL_KEYWORDS or _FORBIDDEN_KEYWORDS_PATTERN.search(stmt):
                raise SolarWindsSecurityError(
                    f"SolarWinds integration is strictly READ-ONLY. Mutating stacked query detected: '{stmt_first_word}'"
                )

    # Check whole query for forbidden mutating statements (e.g. INSERT INTO, UPDATE x, DELETE FROM)
    # Check if forbidden words appear outside of SELECT column list where prohibited
    for match in _FORBIDDEN_KEYWORDS_PATTERN.finditer(cleaned):
        matched_word = match.group(1).upper()
        # If the matched word is in FORBIDDEN_SWQL_KEYWORDS, verify context
        # For SELECT queries, words like 'EXEC' or 'DELETE' or 'DROP' should never be valid keywords
        if matched_word in FORBIDDEN_SWQL_KEYWORDS:
            # Suffix check to ensure it's not a function parameter or column alias unless it's a DDL/DML verb
            # But in SWQL, none of these keywords are valid tokens in a pure SELECT query
            raise SolarWindsSecurityError(
                f"SolarWinds integration is strictly READ-ONLY. Forbidden mutating keyword detected: '{matched_word}'"
            )
