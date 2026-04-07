"""
Tests for the public API surface — what users import from mcp_audit_trail.
"""

import mcp_audit_trail


class TestPublicAPI:
    def test_version_is_set(self):
        assert hasattr(mcp_audit_trail, "__version__")
        assert mcp_audit_trail.__version__ == "0.1.0"

    def test_exports_audit_logger(self):
        assert hasattr(mcp_audit_trail, "AuditLogger")

    def test_exports_run_proxy(self):
        assert hasattr(mcp_audit_trail, "run_proxy")
        assert callable(mcp_audit_trail.run_proxy)

    def test_exports_generate_report(self):
        assert hasattr(mcp_audit_trail, "generate_report")
        assert callable(mcp_audit_trail.generate_report)

    def test_all_matches_exports(self):
        for name in mcp_audit_trail.__all__:
            assert hasattr(mcp_audit_trail, name)
