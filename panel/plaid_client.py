"""Thin wrapper around plaid-python for the /panel/bank/ real-time feed.

All functions raise plaid.ApiException on API errors; callers handle/log.
`is_configured()` lets the UI fall back to the demo flow when keys are absent.
"""
import hashlib
import hmac
import json
import time
from decimal import Decimal
from django.conf import settings

import jwt
import plaid
from plaid.api import plaid_api
from plaid.api_client import ApiClient
from plaid.configuration import Configuration
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.country_code import CountryCode
from plaid.model.products import Products
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.item_get_request import ItemGetRequest
from plaid.model.institutions_get_by_id_request import InstitutionsGetByIdRequest
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from plaid.model.webhook_verification_key_get_request import (
    WebhookVerificationKeyGetRequest,
)


_ENV_HOSTS = {
    "sandbox": plaid.Environment.Sandbox,
    "production": plaid.Environment.Production,
}


def is_configured():
    return bool(settings.PLAID_CLIENT_ID and settings.PLAID_SECRET)


def _client():
    config = Configuration(
        host=_ENV_HOSTS.get(settings.PLAID_ENV, plaid.Environment.Sandbox),
        api_key={"clientId": settings.PLAID_CLIENT_ID, "secret": settings.PLAID_SECRET},
    )
    return plaid_api.PlaidApi(ApiClient(config))


def create_link_token(user_id, access_token=None):
    """Return a short-lived link_token used to open Plaid Link in the browser.

    Pass `access_token` for *update mode* — re-authenticating an item the bank
    has locked out (ITEM_LOGIN_REQUIRED). Update-mode tokens must not carry
    `products`; Plaid rejects the pair.
    """
    kwargs = dict(
        user=LinkTokenCreateRequestUser(client_user_id=str(user_id)),
        client_name="Garage Lions",
        country_codes=[CountryCode("US")],
        language="en",
    )
    if access_token:
        kwargs["access_token"] = access_token
    else:
        kwargs["products"] = [Products("transactions")]
    # Required for OAuth institutions — without it Link can't hand off to the
    # bank's own site and back. Must be pre-registered in the Plaid dashboard.
    if settings.PLAID_REDIRECT_URI:
        kwargs["redirect_uri"] = settings.PLAID_REDIRECT_URI
    if settings.PLAID_WEBHOOK_URL:
        kwargs["webhook"] = settings.PLAID_WEBHOOK_URL
    return _client().link_token_create(LinkTokenCreateRequest(**kwargs)).link_token


def verify_webhook(body, verification_header):
    """True if `body` (raw request bytes) genuinely came from Plaid.

    Plaid signs every webhook with an ES256 JWT in the Plaid-Verification
    header. We fetch the matching public key, check the token, reject anything
    older than 5 minutes (replay), and confirm the body hash in the claims
    matches what we actually received.
    """
    if not verification_header:
        return False
    try:
        header = jwt.get_unverified_header(verification_header)
    except jwt.PyJWTError:
        return False
    # Plaid only ever signs ES256; anything else is an algorithm-confusion probe.
    if header.get("alg") != "ES256" or not header.get("kid"):
        return False
    try:
        jwk = _client().webhook_verification_key_get(
            WebhookVerificationKeyGetRequest(key_id=header["kid"])
        ).key.to_dict()
        public_key = jwt.algorithms.ECAlgorithm.from_jwk(
            json.dumps({k: jwk[k] for k in ("kty", "crv", "x", "y")})
        )
        claims = jwt.decode(verification_header, key=public_key, algorithms=["ES256"])
    except (plaid.ApiException, jwt.PyJWTError, KeyError, ValueError):
        return False
    if time.time() - claims.get("iat", 0) > 5 * 60:
        return False
    return hmac.compare_digest(
        claims.get("request_body_sha256", ""), hashlib.sha256(body).hexdigest()
    )


def exchange_public_token(public_token):
    """Swap the one-time public_token from Link for a durable access_token."""
    resp = _client().item_public_token_exchange(
        ItemPublicTokenExchangeRequest(public_token=public_token)
    )
    return resp.access_token, resp.item_id


def get_institution(access_token):
    """Best-effort (institution_id, institution_name) for an item."""
    client = _client()
    try:
        item = client.item_get(ItemGetRequest(access_token=access_token)).item
        inst_id = item.institution_id
        if not inst_id:
            return "", ""
        inst = client.institutions_get_by_id(
            InstitutionsGetByIdRequest(
                institution_id=inst_id, country_codes=[CountryCode("US")]
            )
        ).institution
        return inst_id, inst.name
    except Exception:
        return "", ""


def get_accounts(access_token):
    """List of dicts: account_id, name, mask, type, current balance."""
    resp = _client().accounts_get(AccountsGetRequest(access_token=access_token))
    out = []
    for a in resp.accounts:
        bal = a.balances
        current = bal.current if bal and bal.current is not None else 0
        out.append({
            "account_id": a.account_id,
            "name": a.name or (a.official_name or "Account"),
            "mask": a.mask or "",
            "type": str(a.subtype or a.type or ""),
            "balance": Decimal(str(current)),
        })
    return out


def sync_transactions(access_token, cursor=""):
    """Incremental pull. Returns (added, modified, removed_ids, next_cursor).

    `added`/`modified` are dicts already normalised to OUR sign convention
    (positive = money into the account) with keys:
    plaid_txn_id, account_id, date, name, amount, pending.
    """
    client = _client()
    added, modified, removed = [], [], []
    has_more = True
    while has_more:
        resp = client.transactions_sync(
            TransactionsSyncRequest(access_token=access_token, cursor=cursor or "")
        )
        for t in resp.added:
            added.append(_norm_txn(t))
        for t in resp.modified:
            modified.append(_norm_txn(t))
        for t in resp.removed:
            removed.append(t.transaction_id)
        cursor = resp.next_cursor
        has_more = resp.has_more
    return added, modified, removed, cursor


def _norm_txn(t):
    # Plaid: positive amount = money leaving the account. We invert so that
    # positive = money in (matches our BankTransaction.amount convention).
    amount = Decimal(str(t.amount)) * Decimal("-1")
    d = getattr(t, "authorized_date", None) or t.date
    name = getattr(t, "merchant_name", None) or t.name
    return {
        "plaid_txn_id": t.transaction_id,
        "account_id": t.account_id,
        "date": d,
        "name": name or "",
        "amount": amount,
        "pending": bool(t.pending),
    }
