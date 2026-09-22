from django.conf import settings
from apps.ai.schemas import StoryboardPlan

class BudgetExceededError(Exception):
    pass

class SceneLimitExceededError(Exception):
    pass

class AgentSafetyValidator:
    """Enforces safety guardrails, budget limits, and scene caps on Super Agent plans."""

    @classmethod
    def validate_plan(cls, plan: StoryboardPlan, user_wallet, strict_balance: bool = True) -> bool:
        max_credits = int(getattr(settings, 'MAX_AGENT_CREDITS_PER_REQUEST', 500000))
        max_scenes = int(getattr(settings, 'MAX_SCENES_PER_REQUEST', 6))

        if len(plan.scenes) > max_scenes:
            raise SceneLimitExceededError(
                f"Agent plan generated {len(plan.scenes)} scenes, which exceeds the limit of {max_scenes} scenes per request."
            )

        # Recompute server-side cost across all scenes to prevent client-side budget tampering
        calculated_credits = 0
        from apps.providers.router import ModelRouter
        for s in plan.scenes:
            try:
                m = ModelRouter.select_model(modality='video', user_preference=getattr(s, 'model_preference', 'automatic') or 'automatic', duration=s.duration)
                calculated_credits += m.calculate_credit_cost(s.duration)
            except Exception:
                rate = getattr(settings, 'CREDIT_COST_VIDEO_PER_SEC', 50)
                calculated_credits += 50 + (s.duration * rate)

        plan.estimated_total_credits = max(plan.estimated_total_credits, calculated_credits)

        if strict_balance:
            if plan.estimated_total_credits > max_credits:
                raise BudgetExceededError(
                    f"Agent plan estimated cost ({plan.estimated_total_credits} credits) exceeds maximum allowed safety cap of {max_credits} credits."
                )

            if user_wallet.balance < plan.estimated_total_credits:
                raise BudgetExceededError(
                    f"Your credit balance ({user_wallet.balance} credits) is insufficient for this plan ({plan.estimated_total_credits} credits required)."
                )

        return True
