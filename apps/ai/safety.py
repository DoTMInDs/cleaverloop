from django.conf import settings
from apps.ai.schemas import StoryboardPlan

class BudgetExceededError(Exception):
    pass

class SceneLimitExceededError(Exception):
    pass

class AgentSafetyValidator:
    """Enforces safety guardrails, budget limits, and scene caps on Super Agent plans."""

    @classmethod
    def validate_plan(cls, plan: StoryboardPlan, user_wallet) -> bool:
        max_credits = getattr(settings, 'MAX_AGENT_CREDITS_PER_REQUEST', 2500)
        max_scenes = getattr(settings, 'MAX_SCENES_PER_REQUEST', 6)

        if len(plan.scenes) > max_scenes:
            raise SceneLimitExceededError(
                f"Agent plan generated {len(plan.scenes)} scenes, which exceeds the limit of {max_scenes} scenes per request."
            )

        if plan.estimated_total_credits > max_credits:
            raise BudgetExceededError(
                f"Agent plan estimated cost ({plan.estimated_total_credits} credits) exceeds maximum allowed safety cap of {max_credits} credits."
            )

        if user_wallet.balance < plan.estimated_total_credits:
            raise BudgetExceededError(
                f"Your credit balance ({user_wallet.balance} credits) is insufficient for this plan ({plan.estimated_total_credits} credits required)."
            )

        return True
