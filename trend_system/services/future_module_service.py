from __future__ import annotations

from trend_system.models import FutureModuleRequest, FutureModuleResult


def prepare_future_module(request: FutureModuleRequest) -> FutureModuleResult:
    """Reserved service contract for the next standalone module.

    This function intentionally does not implement business behavior yet.
    Its purpose is to stabilize the integration boundary now, so the future
    module can plug into services, interfaces, and tests without requiring
    another architecture pass first.
    """
    return FutureModuleResult(
        module_key=request.module_key,
        enabled=False,
        status="reserved",
        notes=(
            "Reserved service slot. Implement the future module here when the "
            "follow-up task is ready."
        ),
    )
