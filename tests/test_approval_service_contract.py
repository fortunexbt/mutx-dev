"""The approval service module is transport/DTO-only, never process state."""

from src.api.services import approval


def test_approval_service_module_has_no_process_local_singleton() -> None:
    assert hasattr(approval, "ApprovalRequest")
    assert hasattr(approval, "ApprovalStatus")
    assert hasattr(approval, "post_approval_webhook")
    assert not hasattr(approval, "ApprovalService")
    assert not hasattr(approval, "get_approval_service")
    assert not hasattr(approval, "_approval_service")
