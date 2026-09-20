import hmac
import hashlib
import json
import logging
import uuid
import requests
from django.conf import settings
from apps.billing.models import SubscriptionPlan

logger = logging.getLogger(__name__)

import time

class CurrencyService:
    """Service to manage dynamic currency conversions between USD and local settlement currencies."""
    _cached_rate = None
    _last_fetched = 0

    @classmethod
    def get_usd_to_ghs_rate(cls) -> float:
        """
        Get USD to GHS exchange rate.
        Checks settings.USD_TO_GHS_RATE first. If 'auto' or unset, queries live rates with 1hr caching.
        """
        configured_rate = getattr(settings, 'USD_TO_GHS_RATE', 'auto')
        if configured_rate != 'auto':
            try:
                return float(configured_rate)
            except (ValueError, TypeError):
                pass

        now = time.time()
        # Cache live rate in memory for 1 hour (3600 seconds)
        if cls._cached_rate and (now - cls._last_fetched) < 3600:
            return cls._cached_rate

        try:
            resp = requests.get('https://open.er-api.com/v6/latest/USD', timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                rate = data.get('rates', {}).get('GHS')
                if rate and float(rate) > 0:
                    cls._cached_rate = round(float(rate), 2)
                    cls._last_fetched = now
                    logger.info(f"Updated live USD to GHS exchange rate: 1 USD = {cls._cached_rate} GHS")
                    return cls._cached_rate
        except Exception as e:
            logger.warning(f"Failed to fetch live exchange rate: {e}")

        # Fallback default if offline
        return cls._cached_rate or 11.58

    @classmethod
    def convert_usd_to_ghs(cls, usd_amount: float) -> tuple[float, float]:
        """Convert a USD amount to GHS based on current rate. Returns (ghs_amount, exchange_rate)."""
        rate = cls.get_usd_to_ghs_rate()
        ghs = round(float(usd_amount) * rate, 2)
        return ghs, rate


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
        """Ensure the SubscriptionPlan has a valid Paystack plan_code on the current integration."""
        if cls.is_mock_mode():
            if not plan.paystack_plan_code or not plan.paystack_plan_code.startswith("PLN_mock_"):
                mock_code = f"PLN_mock_{plan.slug}"
                plan.paystack_plan_code = mock_code
                plan.save(update_fields=['paystack_plan_code'])
            return plan.paystack_plan_code

        # In live Paystack mode:
        # Check if already configured with a genuine Paystack code and verify it exists on current account
        if (
            plan.paystack_plan_code
            and not plan.paystack_plan_code.startswith("PLN_mock_")
            and plan.paystack_plan_code != f"PLN_{plan.slug}"
        ):
            try:
                chk = requests.get(f"{cls.BASE_URL}/plan/{plan.paystack_plan_code}", headers=cls._headers(), timeout=10)
                if chk.status_code == 200 and chk.json().get('status'):
                    return plan.paystack_plan_code
                else:
                    logger.warning(
                        f"Stored plan code {plan.paystack_plan_code} not found on current Paystack integration. Re-syncing."
                    )
            except Exception as e:
                logger.warning(f"Error checking plan on Paystack: {e}")
                return plan.paystack_plan_code

        currency = getattr(settings, 'PAYSTACK_CURRENCY', 'GHS')
        if currency.upper() == 'GHS':
            ghs_amount, rate = CurrencyService.convert_usd_to_ghs(plan.price_monthly)
            amount_kobo = int(round(ghs_amount * 100))
            plan_name = f"CleaverLoop AI - {plan.name} (${plan.price_monthly:.0f} USD)"
            plan_desc = f"${plan.price_monthly:.2f} USD/mo converted to GHS (~GHS {ghs_amount:,.2f}) at 1 USD = {rate:.2f} GHS"
        else:
            amount_kobo = int(plan.price_monthly * 100)
            plan_name = f"CleaverLoop AI - {plan.name}"
            plan_desc = plan.tagline or f"Monthly {plan.name} Membership"

        # 1. Search existing plans on Paystack to avoid duplicate plan creation
        try:
            resp = requests.get(f"{cls.BASE_URL}/plan", headers=cls._headers(), timeout=15)
            if resp.status_code == 200 and resp.json().get('status'):
                for p in resp.json().get('data', []):
                    if plan.name.lower() in p.get('name', '').lower() and p.get('plan_code'):
                        real_code = p['plan_code']
                        plan.paystack_plan_code = real_code
                        plan.save(update_fields=['paystack_plan_code'])
                        logger.info(f"Linked existing Paystack plan '{p.get('name')}' -> {real_code}")
                        return real_code
        except Exception as e:
            logger.warning(f"Unable to query existing Paystack plans: {e}")

        # 2. Create new plan on Paystack
        payload = {
            "name": plan_name,
            "interval": "monthly",
            "amount": amount_kobo,
            "currency": currency,
            "description": plan_desc,
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

        return ""

    @classmethod
    def initialize_transaction(cls, user, plan: SubscriptionPlan, callback_url: str) -> dict:
        """Initialize payment transaction with Paystack and return checkout authorization URL."""
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

        plan_code = cls.get_or_create_plan(plan)
        if not plan_code:
            currency = getattr(settings, 'PAYSTACK_CURRENCY', 'GHS')
            err = (
                f"Could not resolve subscription plan for '{plan.name}' on Paystack. "
                f"Ensure PAYSTACK_CURRENCY ({currency}) matches your Paystack account country."
            )
            logger.error(err)
            return {"status": False, "message": err}

        currency = getattr(settings, 'PAYSTACK_CURRENCY', 'GHS')
        if currency.upper() == 'GHS':
            ghs_amount, rate = CurrencyService.convert_usd_to_ghs(plan.price_monthly)
            amount_subunit = int(round(ghs_amount * 100))
        else:
            ghs_amount = float(plan.price_monthly)
            rate = 1.0
            amount_subunit = int(plan.price_monthly * 100)

        payload = {
            "email": user.email,
            "amount": amount_subunit,
            "plan": plan_code,
            "callback_url": callback_url,
            "metadata": {
                "user_id": str(user.id),
                "user_email": user.email,
                "plan_id": str(plan.id),
                "plan_slug": plan.slug,
                "credits_per_month": plan.credits_per_month,
                "usd_price": f"${plan.price_monthly:.2f} USD",
                "exchange_rate": f"1 USD = {rate:.2f} GHS",
                "custom_fields": [
                    {
                        "display_name": "Selected Plan",
                        "variable_name": "selected_plan",
                        "value": f"{plan.name} (${plan.price_monthly:.2f} USD / mo)"
                    },
                    {
                        "display_name": "Price in USD",
                        "variable_name": "price_in_usd",
                        "value": f"${plan.price_monthly:.2f} USD"
                    },
                    {
                        "display_name": "Exchange Rate",
                        "variable_name": "exchange_rate",
                        "value": f"1 USD = {rate:.2f} GHS"
                    },
                    {
                        "display_name": "Total in Cedis",
                        "variable_name": "total_in_cedis",
                        "value": f"GHS {ghs_amount:,.2f}"
                    }
                ]
            }
        }
        # Only pass explicit currency if not USD or if currency is enabled for merchant
        if currency and currency.upper() != 'USD':
            payload["currency"] = currency.upper()

        try:
            resp = requests.post(f"{cls.BASE_URL}/transaction/initialize", headers=cls._headers(), json=payload, timeout=15)
            data = resp.json()
            if resp.status_code == 200 and data.get('status'):
                return data
            else:
                msg = data.get('message', 'Failed to initialize transaction with Paystack.')
                logger.error(f"Paystack initialize failed: {msg}")
                return {"status": False, "message": msg}
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
