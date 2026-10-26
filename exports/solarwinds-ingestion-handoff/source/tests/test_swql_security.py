"""Read-only SWQL validation against the actual source security guard."""
import unittest
from app.core.security import SolarWindsSecurityError, validate_swql_read_only


class TestReadOnlySWQLValidatorAndSecurityGuards(unittest.TestCase):
    """Validates strictly read-only SWQL query parser and SQL injection blockers."""

    def test_valid_select_query_accepted(self):
        """Valid SELECT queries must pass validation."""
        valid_queries = [
            "SELECT NodeID, Caption, IPAddress FROM Orion.Nodes",
            "  SELECT n.NodeID, n.Status FROM Orion.Nodes n WHERE n.Status = 1  ",
            "SELECT TOP 100 Caption, CPULoad FROM Orion.Nodes ORDER BY CPULoad DESC",
        ]
        for q in valid_queries:
            validate_swql_read_only(q)

    def test_dml_mutating_keywords_rejected(self):
        """DML mutating commands (INSERT, UPDATE, DELETE) must raise SolarWindsSecurityError."""
        mutations = [
            "INSERT INTO Orion.Nodes (Caption) VALUES ('hacked')",
            "UPDATE Orion.Nodes SET Status = 2 WHERE NodeID = 1",
            "DELETE FROM Orion.Nodes WHERE NodeID = 10",
            "SELECT * FROM Orion.Nodes; DELETE FROM Orion.Nodes",
        ]
        for q in mutations:
            with self.assertRaises(SolarWindsSecurityError, msg=f"Failed to reject: {q}"):
                validate_swql_read_only(q)

    def test_ddl_mutating_keywords_rejected(self):
        """DDL commands (DROP, ALTER, CREATE, TRUNCATE, EXEC) must raise SolarWindsSecurityError."""
        ddls = [
            "DROP TABLE Orion.Nodes",
            "ALTER TABLE Orion.Nodes ADD COLUMN pwned INT",
            "TRUNCATE TABLE Orion.Nodes",
            "EXEC sp_executesql 'SELECT 1'",
            "GRANT ALL PRIVILEGES ON Orion.Nodes TO public",
        ]
        for q in ddls:
            with self.assertRaises(SolarWindsSecurityError, msg=f"Failed to reject: {q}"):
                validate_swql_read_only(q)

    def test_comment_obfuscation_rejected(self):
        """Obfuscated queries disguised with SQL comments must be rejected."""
        obfuscated = [
            "-- Dangerous query\nDELETE FROM Orion.Nodes",
            "/* Comment */ DROP TABLE Orion.Nodes",
        ]
        for q in obfuscated:
            with self.assertRaises(SolarWindsSecurityError, msg=f"Failed to reject: {q}"):
                validate_swql_read_only(q)

    def test_column_names_containing_keywords_not_falsely_rejected(self):
        """Queries containing columns like LastUpdatedDate must NOT be falsely rejected."""
        query = "SELECT NodeID, Caption, LastUpdatedDate, InsertTime FROM Orion.Nodes"
        validate_swql_read_only(query)

    def test_subquery_union_injection_attack_rejected(self):
        """Attacks attempting stacked queries or injected mutation statements are blocked."""
        with self.assertRaises(SolarWindsSecurityError):
            validate_swql_read_only("SELECT Caption FROM Orion.Nodes WHERE NodeID = 1; TRUNCATE TABLE Orion.Nodes")
