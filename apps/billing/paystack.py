import hmac
import hashlib
import json
import logging
import uuid
import requests
from django.conf import settings
from apps.billing.models import SubscriptionPlan

logger = logging.getLogger(__name__)

class PaystackService:
    BASE_URL = "https://api.paystack.co"

    @classmethod
    def get_secret_key(cls) -> str:
        return getattr(settings, 'PAYSTACK_SECRET_KEY', '')

    @classmethod
    def is_mock_mode(cls) -> bool:
        provider = getattr(settings, 'PAYMENT_PROVIDER', 'mock').lower()
        secret_key = cls.get_secret_key()
        return provider == 'mock' or not secret_key

    @classmethod
    def _headers(cls) -> dict:
        return {
            "Authorization": f"Bearer {cls.get_secret_key()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @classmethod
    def get_or_create_plan(cls, plan: SubscriptionPlan) -> str:
        """Ensure the SubscriptionPlan has a Paystack plan_code."""
        if plan.paystack_plan_code:
            return plan.paystack_plan_code

        if cls.is_mock_mode():
            mock_code = f"PLN_mock_{plan.slug}"
            plan.paystack_plan_code = mock_code
            plan.save(update_fields=['paystack_plan_code'])
            return mock_code

        currency = getattr(settings, 'PAYSTACK_CURRENCY', 'USD')
        # Amount in smallest currency unit (cents or kobo)
        amount_kobo = int(plan.price_monthly * 100)

        payload = {
            "name": f"CleaverLoop AI - {plan.name}",
            "interval": "monthly",
            "amount": amount_kobo,
            "currency": currency,
            "description": plan.tagline or f"Monthly {plan.name} Membership",
        }

        try:
            resp = requests.post(f"{cls.BASE_URL}/plan", headers=cls._headers(), json=payload, timeout=15)
            data = resp.json()
            if resp.status_code in (200, 201) and data.get('status'):
                plan_code = data['data']['plan_code']
                plan.paystack_plan_code = plan_code
                plan.save(update_fields=['paystack_plan_code'])
                return plan_code
            else:
                logger.error(f"Paystack create plan failed: {data.get('message')}")
        except Exception as e:
            logger.error(f"Paystack connection error in get_or_create_plan: {e}")

        # Fallback generated reference if offline
        fallback_code = f"PLN_{plan.slug}"
        plan.paystack_plan_code = fallback_code
        plan.save(update_fields=['paystack_plan_code'])
        return fallback_code

    @classmethod
    def initialize_transaction(cls, user, plan: SubscriptionPlan, callback_url: str) -> dict:
        """Initialize payment transaction with Paystack and return checkout authorization URL."""
        plan_code = cls.get_or_create_plan(plan)
        amount_subunit = int(plan.price_monthly * 100)

        if cls.is_mock_mode():
            mock_ref = f"mock_ref_{uuid.uuid4().hex[:14]}"
            mock_checkout_url = f"{callback_url}?reference={mock_ref}&plan_id={plan.id}"
            return {
                "status": True,
                "data": {
                    "authorization_url": mock_checkout_url,
                    "reference": mock_ref,
                    "access_code": f"access_{mock_ref}",
                }
            }

        currency = getattr(settings, 'PAYSTACK_CURRENCY', 'USD')
        payload = {
            "email": user.email,
            "amount": amount_subunit,
            "plan": plan_code,
            "callback_url": callback_url,
            "currency": currency,
            "metadata": {
                "user_id": str(user.id),
                "user_email": user.email,
                "plan_id": str(plan.id),
                "plan_slug": plan.slug,
                "credits_per_month": plan.credits_per_month,
            }
        }

        try:
            resp = requests.post(f"{cls.BASE_URL}/transaction/initialize", headers=cls._headers(), json=payload, timeout=15)
            data = resp.json()
            if resp.status_code == 200 and data.get('status'):
                return data
            else:
                logger.error(f"Paystack initialize failed: {data.get('message')}")
                return {"status": False, "message": data.get('message', 'Failed to initialize transaction with Paystack.')}
        except Exception as e:
            logger.error(f"Paystack transaction initialize exception: {e}")
            return {"status": False, "message": f"Connection error: {str(e)}"}

    @classmethod
    def verify_transaction(cls, reference: str) -> dict:
        """Verify transaction authenticity and payment status with Paystack."""
        if cls.is_mock_mode():
            return {
                "status": True,
                "data": {
                    "status": "success",
                    "reference": reference,
                    "amount": 0,
                    "gateway_response": "Successful (Mock Mode)",
                    "customer": {
                        "customer_code": "CUS_mock_test",
                        "email": "subscriber@cleaverloop.ai",
                    },
                    "authorization": {
                        "authorization_code": "AUTH_mock_123",
                        "card_type": "visa",
                        "last4": "4081",
                        "exp_month": "12",
                        "exp_year": "2030",
                    },
                    "plan_object": {},
                }
            }

        if reference.startswith("mock_ref_"):
            logger.warning(f"Rejected mock transaction reference '{reference}' while in live payment mode.")
            return {"status": False, "message": "Invalid transaction reference for live payment provider."}

        try:
            resp = requests.get(f"{cls.BASE_URL}/transaction/verify/{reference}", headers=cls._headers(), timeout=15)
            return resp.json()
        except Exception as e:
            logger.error(f"Paystack verify exception for reference {reference}: {e}")
            return {"status": False, "message": f"Verification error: {str(e)}"}

    @classmethod
    def disable_subscription(cls, subscription_code: str, email_token: str) -> bool:
        """Cancel a subscription via Paystack API."""
        if cls.is_mock_mode():
            return True

        if subscription_code.startswith("mock_"):
            logger.warning(f"Rejected mock subscription code '{subscription_code}' in live payment mode.")
            return False

        payload = {
            "code": subscription_code,
            "token": email_token
        }
        try:
            resp = requests.post(f"{cls.BASE_URL}/subscription/disable", headers=cls._headers(), json=payload, timeout=15)
            data = resp.json()
            return data.get('status', False)
        except Exception as e:
            logger.error(f"Paystack disable subscription error: {e}")
            return False

    @classmethod
    def verify_webhook_signature(cls, request_body: bytes, signature_header: str) -> bool:
        """Validate HMAC SHA512 signature on incoming Paystack webhooks."""
        secret = cls.get_secret_key()
        if not secret:
            return False
        computed_hash = hmac.new(secret.encode('utf-8'), request_body, hashlib.sha512).hexdigest()
        return hmac.compare_digest(computed_hash, signature_header or '')
