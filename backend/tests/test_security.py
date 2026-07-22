"""
Security-regression tests for the audit hardening. All pure — no DB, no
WeasyPrint native libs — so they run everywhere including Windows hosts.

Covers:
  - PDF template autoescaping + WeasyPrint data:-only URL fetcher (HTML
    injection / SSRF / local-file read via a hostile customer/estimate field).
  - Token credential-watermark revocation (session invalidation on password
    change/reset).
  - PERCENTAGE discount cap (no negative totals).
  - company logo_data_url must be an inline data: URI.
"""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from starlette.requests import Request

from app.services.pdf import render_estimate_html, _data_only_url_fetcher
from app.services.auth import (
    create_access_token, create_refresh_token, decode_token,
    token_watermark_matches, mark_password_changed, _pwd_watermark,
)
from app.schemas.estimate import EstimateCreate, EstimateUpdate
from app.schemas.company import CompanySettingsUpdate
from app.schemas.customer import CustomerCreate
from app.services.pricing import _apply_commercial_terms
from app.services.ratelimit import client_ip


# ─── Fixtures ───────────────────────────────────────────────────────

def _estimate_with(customer_field: str, value: str):
    """A minimal estimate whose `customer_field` carries an injection payload."""
    customer = SimpleNamespace(
        name="Acme", company="", phone="", email="", address="", gstin="",
    )
    setattr(customer, customer_field, value)
    return SimpleNamespace(
        number=1, revision=1, title="T", notes="", terms="", status="draft",
        quote_date=date(2026, 1, 1), valid_until=date(2026, 2, 1),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        discount_type=None, discount_value=0, discount_amount=0, subtotal=0,
        other_charges=[], taxable=0, gst=0, gst_pct=18, grand_total=0,
        advance_pct=0, advance_amount=0, customer=customer, frames=[],
    )


# ─── PDF injection ──────────────────────────────────────────────────

def test_pdf_autoescapes_hostile_customer_field():
    payload = '<img src=x onerror="alert(1)">PWN'
    html = render_estimate_html(_estimate_with("name", payload), None)
    assert "<img src=x onerror" not in html      # raw markup neutralized
    assert "&lt;img src=x onerror" in html        # rendered as inert text


def test_pdf_autoescapes_hostile_notes():
    est = _estimate_with("name", "Acme")
    est.notes = "<script>steal()</script>"
    html = render_estimate_html(est, None)
    assert "<script>steal" not in html
    assert "&lt;script&gt;" in html


@pytest.mark.parametrize("bad", [
    "file:///etc/passwd", "http://169.254.169.254/latest/meta-data/",
    "https://internal.svc/secret", "FILE:///etc/shadow",
])
def test_pdf_url_fetcher_blocks_non_data_urls(bad):
    with pytest.raises(ValueError):
        _data_only_url_fetcher(bad)


# ─── Session invalidation (token watermark) ─────────────────────────

def _user(changed_at=None):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        created_at=now, password_changed_at=changed_at or now,
    )


def test_fresh_access_token_validates():
    u = _user()
    assert token_watermark_matches(u, decode_token(create_access_token(u)))


def test_token_rejected_after_password_change():
    # Mint against a fixed prior instant, then advance the watermark — mirrors a
    # password change after the token was issued. (Explicit delta rather than a
    # wall-clock now(), whose coarse resolution on some OSes makes back-to-back
    # calls collide.)
    u = _user(changed_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    tok = create_access_token(u)
    u.password_changed_at = u.password_changed_at + timedelta(seconds=1)
    assert not token_watermark_matches(u, decode_token(tok))


def test_refresh_token_rejected_after_password_change():
    u = _user()
    tok = create_refresh_token(u)
    u.password_changed_at = u.password_changed_at + timedelta(seconds=1)
    assert not token_watermark_matches(u, decode_token(tok))


def test_token_without_pwd_claim_is_rejected():
    # A legacy token minted before the claim existed must not validate.
    assert not token_watermark_matches(_user(), {"sub": "x", "type": "access"})


def test_mark_password_changed_moves_watermark_forward():
    u = _user(changed_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
    before = _pwd_watermark(u)
    mark_password_changed(u)
    assert _pwd_watermark(u) > before


# ─── Discount cap ───────────────────────────────────────────────────

def test_percentage_discount_over_100_rejected_on_create():
    with pytest.raises(ValidationError):
        EstimateCreate(discount_type="PERCENTAGE", discount_value=150)


def test_percentage_discount_over_100_rejected_on_update():
    with pytest.raises(ValidationError):
        EstimateUpdate(discount_type="PERCENTAGE", discount_value=101)


def test_flat_discount_over_100_still_allowed():
    # FLAT is an absolute ₹ amount, clamped to the subtotal at pricing time.
    EstimateCreate(discount_type="FLAT", discount_value=100000)


def test_pricing_clamps_runaway_percentage_discount():
    # Defense in depth: a stored/legacy >100% value must not go negative.
    terms = _apply_commercial_terms(1000, "PERCENTAGE", 150, 0, gst_pct=18)
    assert terms["taxable"] == 0.0
    assert terms["grand_total"] == 0


# ─── Company logo must be a data: URI ───────────────────────────────

@pytest.mark.parametrize("bad", [
    "http://evil.example/logo.png", "file:///etc/passwd", "javascript:alert(1)",
])
def test_logo_data_url_rejects_non_data_uri(bad):
    with pytest.raises(ValidationError):
        CompanySettingsUpdate(logo_data_url=bad)


def test_logo_data_url_accepts_data_uri():
    CompanySettingsUpdate(logo_data_url="data:image/png;base64,AAAA")


# ─── Customer field validation ──────────────────────────────────────

def test_customer_rejects_invalid_email():
    with pytest.raises(ValidationError):
        CustomerCreate(name="X", email="not-an-email")


def test_customer_rejects_overlong_address():
    with pytest.raises(ValidationError):
        CustomerCreate(name="X", address="a" * 501)


# ─── Rate-limit key: real client behind the nginx reverse proxy ─────
#
# Behind nginx the socket peer is always the proxy, so keying on it would put
# every user in one shared bucket (one actor could exhaust the 5/min login
# limit for everyone). The key must follow nginx's authoritative X-Real-IP.

def _req(headers: dict, client=("10.0.0.9", 51000)) -> Request:
    return Request({
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": client,
    })


def test_rate_limit_key_prefers_x_real_ip():
    # Two different real clients arriving through the same proxy socket must key
    # on distinct IPs, not collapse onto the proxy's address.
    a = client_ip(_req({"x-real-ip": "203.0.113.7"}))
    b = client_ip(_req({"x-real-ip": "198.51.100.4"}))
    assert a == "203.0.113.7"
    assert b == "198.51.100.4"
    assert a != b


def test_rate_limit_key_falls_back_to_socket_without_proxy():
    # Dev / direct connection: no proxy header, so key on the socket address.
    assert client_ip(_req({})) == "10.0.0.9"


def test_rate_limit_key_ignores_forwarded_for_list_tail():
    # Only the first (nginx-attested) hop is trusted; a client-prepended value
    # must not be able to rotate identity to dodge the limit.
    assert client_ip(_req({"x-real-ip": "203.0.113.7, 70.0.0.1"})) == "203.0.113.7"
