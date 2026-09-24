import json
import logging
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from apps.accounts.models import User
from apps.billing.models import SubscriptionPlan, Subscription
from apps.billing.paystack import PaystackService
from apps.credits.models import CreditTransaction
from apps.credits.services import CreditService

logger = logging.getLogger(__name__)

@csrf_exempt
@require_POST
def paystack_webhook_view(request):
    """
    Idempotent Paystack webhook listener.
    Cryptographically validates HMAC SHA512 signature and processes subscription lifecycles.
    """
    signature = request.headers.get('x-paystack-signature', '')

    # In production with live keys, enforce signature validation
    if not PaystackService.is_mock_mode():
        if not PaystackService.verify_webhook_signature(request.body, signature):
            logger.warning("Rejected Paystack webhook with invalid signature.")
            return HttpResponse("Invalid signature", status=401)

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except Exception as e:
        logger.error(f"Failed to parse webhook JSON payload: {e}")
        return HttpResponse("Malformed JSON", status=400)

    event = payload.get('event')
    data = payload.get('data', {})

    logger.info(f"Received Paystack webhook event: {event}")

    if event == 'charge.success':
        reference = data.get('reference')
        if not reference:
            return HttpResponse("No reference provided", status=200)

        # Idempotency check: Ensure credits are not granted twice for the same payment reference
        external_ref = f"paystack:{reference}"
        if CreditTransaction.objects.filter(external_reference=external_ref).exists():
            logger.info(f"Paystack charge reference {reference} already processed. Skipping duplicate.")
            return HttpResponse("Already processed", status=200)

        # Retrieve user and plan from metadata or customer email
        metadata = data.get('metadata', {}) or {}
        user_id = metadata.get('user_id')
        plan_id = metadata.get('plan_id')
        customer_email = data.get('customer', {}).get('email')

        user = None
        if user_id:
            user = User.objects.filter(id=user_id).first()
        if not user and customer_email:
            user = User.objects.filter(email__iexact=customer_email).first()

        # Top-up credit pack payment
        if metadata.get('payment_type') == 'topup':
            pack_id = metadata.get('pack_id')
            credits_to_grant = int(metadata.get('credits_amount') or 50000)
            from apps.billing.views import InitializeTopupCheckoutView
            pack = InitializeTopupCheckoutView.TOPUP_PACKS.get(pack_id)
            if pack:
                credits_to_grant = pack['credits']
            external_topup_ref = f"paystack:topup:{reference}"
            if not CreditTransaction.objects.filter(external_reference=external_topup_ref).exists() and user:
                try:
                    from django.db import IntegrityError
                    CreditService.grant_credits(
                        user=user,
                        amount=credits_to_grant,
                        transaction_type='purchase',
                        description=f"Top-up credit pack purchase ({credits_to_grant:,} credits)",
                        external_reference=external_topup_ref
                    )
                    logger.info(f"Granted {credits_to_grant} top-up credits to {user.email} via webhook charge {reference}.")
                except IntegrityError:
                    pass
            return HttpResponse("Webhook processed successfully", status=200)

        plan = SubscriptionPlan.resolve_plan(
            plan_id=plan_id,
            slug=metadata.get('plan_slug'),
            paystack_code=data.get('plan')
        )

        if user and plan:
            try:
                CreditService.activate_subscription(
                    user=user,
                    plan=plan,
                    reference=reference,
                    customer_code=data.get('customer', {}).get('customer_code', ''),
                    external_subscription_id=data.get('plan', '') or data.get('subscription_code', ''),
                    grant_monthly_credits=True
                )
                logger.info(f"Activated {plan.name} subscription and synced wallet for {user.email} via Paystack webhook charge {reference}.")
            except Exception as e:
                logger.error(f"Error activating subscription from webhook: {e}")

    elif event == 'subscription.create':
        sub_code = data.get('subscription_code')
        email_token = data.get('email_token')
        customer_email = data.get('customer', {}).get('email')

        if customer_email:
            user = User.objects.filter(email__iexact=customer_email).first()
            if user:
                Subscription.objects.filter(user=user).update(
                    external_subscription_id=sub_code,
                    email_token=email_token,
                    status='active'
                )
                logger.info(f"Linked Paystack subscription {sub_code} to {user.email}.")

    elif event in ('subscription.disable', 'subscription.not_renew'):
        sub_code = data.get('subscription_code')
        if sub_code:
            updated = Subscription.objects.filter(external_subscription_id=sub_code).update(status='canceled')
            logger.info(f"Marked subscription {sub_code} as canceled ({updated} records updated).")

    elif event == 'invoice.payment_failed':
        sub_code = data.get('subscription_code')
        customer_email = data.get('customer', {}).get('email')
        if sub_code:
            updated = Subscription.objects.filter(external_subscription_id=sub_code).update(status='past_due')
            logger.warning(f"Marked subscription {sub_code} as past_due following failed renewal invoice ({updated} records).")
        elif customer_email:
            user = User.objects.filter(email__iexact=customer_email).first()
            if user:
                Subscription.objects.filter(user=user).update(status='past_due')
                logger.warning(f"Marked subscription for {user.email} as past_due following failed renewal invoice.")

    elif event in ('charge.dispute.create', 'charge.dispute.remind'):
        ref = data.get('transaction', {}).get('reference') or data.get('reference')
        logger.critical(f"Paystack payment dispute/chargeback flagged for reference {ref}. Review account status immediately.")

    return HttpResponse("Webhook processed successfully", status=200)
