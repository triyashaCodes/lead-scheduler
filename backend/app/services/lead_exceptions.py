from app.models import LeadState


class LeadError(Exception):
    """Base class for lead domain errors."""


class LeadNotFoundError(LeadError):
    def __init__(self, lead_id: str) -> None:
        super().__init__(f"Lead {lead_id} not found")
        self.lead_id = lead_id


class InvalidStateTransitionError(LeadError):
    def __init__(self, current: LeadState, target: LeadState) -> None:
        super().__init__(f"Cannot move lead from {current.value} to {target.value}")
        self.current = current
        self.target = target
