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

        plan = SubscriptionPlan.resolve_plan(
            plan_id=plan_id,
            slug=metadata.get('plan_slug'),
            paystack_code=data.get('plan')
        )

        if user and plan:
            # Activate or update user's Subscription
            sub, _ = Subscription.objects.update_or_create(
                user=user,
                defaults={
                    'plan': plan,
                    'provider': 'paystack',
                    'status': 'active',
                    'last_payment_reference': reference,
                    'customer_code': data.get('customer', {}).get('customer_code', ''),
                }
            )

            # Atomically ledger monthly credits to the user's wallet
            CreditService.grant_credits(
                user=user,
                amount=plan.credits_per_month,
                transaction_type='subscription_credit',
                description=f"Paystack monthly subscription credits ({plan.name})",
                external_reference=external_ref
            )
            logger.info(f"Granted {plan.credits_per_month} credits to {user.email} via Paystack charge {reference}.")

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

    return HttpResponse("Webhook processed successfully", status=200)
