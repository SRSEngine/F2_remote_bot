# -*- coding: utf-8 -*-
r"""
mslogin.py — ورود خودکار به حساب مایکروسافت (ایکس‌باکس) و ساختن فایل توکن xbrp.

خروجی: یک فایل JSON با همان قالبی که xbrp می‌خواهد (کلید refresh_token و client_id).
xbrp با فلگ -token <همین فایل> از آن استفاده می‌کند و خودش توکن را تازه نگه می‌دارد.

روش کار: صفحه‌ی ورود login.live.com با مرورگر (Edge/Chrome سیستمی، با Playwright) باز می‌شود،
ایمیل و پسورد و کد Google Authenticator (TOTP از روی سکرت Gauth) خودکار پر می‌شوند،
و در پایان کدِ بازگشتی (code=...) گرفته و به refresh_token تبدیل می‌شود.

تست دستیِ یک حساب:
    python mslogin.py --email a@b.com --password *** --gauth ABCD... --out tokens\XBOX.json --show
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
from pathlib import Path

import requests

try:
    import pyotp
except Exception:  # pragma: no cover
    pyotp = None

# همان مقادیری که xbrp در auth.go استفاده می‌کند (کلاینت عمومی ایکس‌باکس).
MSA_CLIENT_ID = "000000004C12AE6F"
MSA_SCOPE = "service::user.auth.xboxlive.com::MBI_SSL"
MSA_REDIRECT = "https://login.live.com/oauth20_desktop.srf"
TOKEN_URL = "https://login.live.com/oauth20_token.srf"


class LoginError(Exception):
    pass


def authorize_url() -> str:
    q = {
        "client_id": MSA_CLIENT_ID,
        "response_type": "code",
        "scope": MSA_SCOPE,
        "redirect_uri": MSA_REDIRECT,
    }
    return "https://login.live.com/oauth20_authorize.srf?" + urllib.parse.urlencode(q)


def totp_now(secret: str) -> str:
    if not secret:
        raise LoginError("2FA code required but Gauth secret is empty")
    if pyotp is None:
        raise LoginError("pyotp is not installed (pip install pyotp)")
    clean = re.sub(r"[\s-]+", "", secret).upper()
    try:
        return pyotp.TOTP(clean).now()
    except Exception:
        raise LoginError("Invalid Google Authenticator secret (must be base32: A-Z and 2-7)")


def totp_fresh(secret: str) -> str:
    """کد TOTP؛ اگر کمتر از ۴ ثانیه به عوض‌شدنش مانده، صبر می‌کند تا کد تازه بیاید."""
    left = 30 - int(time.time()) % 30
    if left < 4:
        time.sleep(left + 0.5)
    return totp_now(secret)


def _otp_input(page):
    """فیلد کد ۶ رقمی (نسخه‌ی قدیم و جدید صفحه‌ی ورود) یا None."""
    for sel in ("input[name=otc]", "#idTxtBx_SAOTCC_OTC", "#codeEntry",
                "input[autocomplete=one-time-code]", "input[inputmode=numeric]", "input[type=tel]"):
        el = page.query_selector(sel)
        if el and el.is_visible():
            return el
    # UI جدید: عنوان «Enter the code …» و یک فیلد متنی با برچسب Code
    try:
        title = page.query_selector("[data-testid=title], h1")
        t = (title.inner_text() if title else "").lower()
        if "code" in t and ("authenticator" in t or "enter the code" in t or "verification" in t):
            for sel in ("input[id^=floatingLabelInput]", "input[type=text]", "input:not([type])"):
                el = page.query_selector(sel)
                if el and el.is_visible() and el.is_editable():
                    return el
    except Exception:
        pass
    return None


def code_to_token(code: str) -> dict:
    """کد authorization را به توکن (شامل refresh_token) تبدیل می‌کند."""
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": MSA_CLIENT_ID,
        "scope": MSA_SCOPE,
        "redirect_uri": MSA_REDIRECT,
    }
    r = requests.post(TOKEN_URL, data=data, timeout=30)
    tok = r.json()
    if not tok.get("access_token") or not tok.get("refresh_token"):
        raise LoginError(f"Code to token exchange failed: {tok.get('error')} {tok.get('error_description')}")
    tok["client_id"] = MSA_CLIENT_ID
    return tok


def _click_if(page, selector: str, timeout: float = 1500) -> bool:
    try:
        el = page.wait_for_selector(selector, timeout=timeout, state="visible")
        if el:
            el.click()
            return True
    except Exception:
        pass
    return False


def _fill_if(page, selector: str, value: str, timeout: float = 1500) -> bool:
    try:
        el = page.wait_for_selector(selector, timeout=timeout, state="visible")
        if el:
            el.fill(value)
            return True
    except Exception:
        pass
    return False


def _submit(page):
    """جلو بردن فرم: اول Enter (مطمئن‌ترین در UI جدید)، بعد دکمه‌های متنی."""
    try:
        page.keyboard.press("Enter")
    except Exception:
        pass
    for name in ("Next", "Sign in", "Submit", "Verify", "Continue"):
        if _click_text(page, name, timeout=400):
            return


def _click_text(page, text: str, timeout: float = 1200) -> bool:
    """روی دکمه/لینکی با این متن کلیک می‌کند (مقاوم به UI جدید React)."""
    pat = re.compile(re.escape(text), re.I)
    for getter in (
        lambda: page.get_by_role("button", name=pat),
        lambda: page.get_by_role("link", name=pat),
        lambda: page.get_by_text(pat),
    ):
        try:
            loc = getter().first
            if loc.count() > 0 and loc.is_visible():
                loc.click(timeout=timeout)
                return True
        except Exception:
            continue
    return False


ERR_DIR = Path(__file__).resolve().parent / "login_errors"


def _fail(page, email, err, log):
    """خطای ورود را با آدرس و عنوان صفحه می‌نویسد، عکس صفحه را ذخیره می‌کند و ۵ ثانیه صبر می‌کند."""
    try:
        url, title = page.url, page.title()
    except Exception:
        url = title = "?"
    log(f"Sign-in FAILED for {email}: {err}")
    log(f"  page: {title} | {url[:120]}")
    try:
        ERR_DIR.mkdir(exist_ok=True)
        shot = ERR_DIR / f"{time.strftime('%m%d_%H%M%S')}_{re.sub(r'[^A-Za-z0-9._-]', '_', email)}.png"
        page.screenshot(path=str(shot))
        log(f"  screenshot: {shot}")
    except Exception:
        pass
    log("  closing the browser in 5 seconds ...")
    try:
        page.wait_for_timeout(5000)
    except Exception:
        time.sleep(5)


def login_and_get_token(email: str, password: str, gauth: str = "",
                        show: bool = False, log=print) -> dict:
    """ورود کامل و برگرداندن دیکشنری توکن. در صورت خطا LoginError می‌دهد."""
    from playwright.sync_api import sync_playwright  # تنبل: فقط وقت نیاز

    if not email or not password:
        raise LoginError("Email or password is empty")

    last_err = None
    for channel in ("msedge", "chrome"):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    channel=channel, headless=not show,
                    args=["--window-size=1180,920", "--window-position=120,60"])
                ctx = browser.new_context(viewport={"width": 1180, "height": 900})
                page = ctx.new_page()
                captured = {"code": None}

                def grab(u: str):
                    if u and u.startswith(MSA_REDIRECT) and "code=" in u:
                        captured["code"] = urllib.parse.parse_qs(
                            urllib.parse.urlparse(u).query).get("code", [None])[0]

                page.on("framenavigated", lambda f: grab(f.url or ""))
                log(f"Opening sign-in page ({channel}) for {email} ...")
                page.goto(authorize_url(), wait_until="domcontentloaded", timeout=60000)

                # # visible mode: allow more time for manual steps if Microsoft asks
                
                try:
                    deadline = time.time() + (300 if show else 120)
                    typed_email = typed_pass = typed_otp = False
                    pw_switch = False
                    while time.time() < deadline and not captured["code"]:
                        grab(page.url or "")
                        if captured["code"]:
                            break

                        # --- خطاهای شناخته‌شده (نسخه‌ی قدیم و جدید) ---
                        try:
                            for err in page.query_selector_all(
                                    "#usernameError, #passwordError, #idTD_Error, [id$=__validationMessage], "
                                    "[role=alert], .alert-error, [aria-live=assertive]"):
                                if not err.is_visible():
                                    continue
                                txt = (err.inner_text() or "").strip()
                                low = txt.lower()
                                if txt and ("incorrect" in low or "wrong" in low or "اشتباه" in txt
                                            or "doesn't match" in low or "try again" in low
                                            or "didn't work" in low or "isn't valid" in low):
                                    raise LoginError(f"Microsoft error: {txt}")
                        except LoginError:
                            raise
                        except Exception:
                            pass

                        # ۱) ایمیل → پر کن و Enter بزن (UI جدید با Enter جلو می‌رود)
                        if not typed_email:
                            em = page.query_selector(
                                "input[type=email], input[name=loginfmt], #usernameEntry, #i0116")
                            if em and em.is_visible():
                                em.fill(email)
                                typed_email = True
                                _submit(page)
                                page.wait_for_timeout(1000)
                                continue

                        # ۲) اگر صفحه‌ی «کد به ایمیل بفرستیم» آمد، به‌جایش «Use your password» را بزن
                        if not typed_pass and not pw_switch:
                            has_pw = page.query_selector(
                                "input[type=password], #passwordEntry, #i0118, input[name=passwd]")
                            if not has_pw and _click_text(page, "Use your password"):
                                pw_switch = True
                                page.wait_for_timeout(1000)
                                continue

                        # ۳) پسورد
                        if not typed_pass:
                            pw = page.query_selector(
                                "input[type=password], #passwordEntry, #i0118, input[name=passwd]")
                            if pw and pw.is_visible():
                                pw.fill(password)
                                typed_pass = True
                                _submit(page)
                                page.wait_for_timeout(1200)
                                continue

                        # ۴) کد Authenticator (TOTP). صفحه‌ی جدید مایکروسافت فقط یک input[type=text] با
                        #    id=floatingLabelInput… و برچسب «Code» دارد (بدون name/autocomplete).
                        if gauth and not typed_otp:
                            otc = _otp_input(page)
                            if otc:
                                code = totp_fresh(gauth)
                                otc.click()
                                otc.fill(code)
                                if (otc.input_value() or "") != code:   # React گاهی fill را نمی‌گیرد
                                    otc.fill("")
                                    otc.type(code, delay=60)
                                typed_otp = True
                                log("Authenticator code entered")
                                # «دیگر روی این دستگاه نپرس» (input مخفی است؛ روی برچسبش کلیک کن)
                                try:
                                    cb = page.query_selector("#trusted-device-checkbox, input[name=AddTD], input[type=checkbox]")
                                    if cb and not cb.is_checked():
                                        lab = page.query_selector("label[for=trusted-device-checkbox]")
                                        (lab or cb).click()
                                except Exception:
                                    pass
                                _submit(page)
                                page.wait_for_timeout(2000)
                                continue

                        # ۵) اگر لیست روش‌های تأیید آمد، گزینه‌ی Authenticator/code را انتخاب کن
                        if gauth and not typed_otp:
                            _click_text(page, "Use a verification code", timeout=500) or                             _click_text(page, "authenticator app", timeout=500) or                             _click_text(page, "verification code", timeout=400)

                        # ۶) «Stay signed in?» / تأیید دسترسی اپ → بله
                        if _click_text(page, "Yes", timeout=500) or \
                           _click_text(page, "Accept", timeout=400) or \
                           _click_text(page, "Continue", timeout=400):
                            page.wait_for_timeout(800)
                            continue

                        page.wait_for_timeout(500)
                except Exception as e:
                    # خطا روی صفحه‌ی ورود (نه باز نشدن مرورگر): مرورگر را ۵ ثانیه باز نگه دار تا دیده شود
                    _fail(page, email, e, log)
                    ctx.close()
                    browser.close()
                    raise LoginError(f"{type(e).__name__}: {e}") from e

                grab(page.url or "")
                code = captured["code"]
                if not code:
                    _fail(page, email, "time ran out, no sign-in code captured", log)
                ctx.close()
                browser.close()
                if not code:
                    raise LoginError("No sign-in code captured (wrong password/2FA, or Microsoft asked for an extra step)")
                log("Code captured, exchanging for token ...")
                return code_to_token(code)
        except LoginError:
            raise
        except Exception as e:  # مرورگر در دسترس نبود → کانال بعدی
            last_err = e
            log(f"Channel {channel} failed: {e}")
            continue
    raise LoginError(f"No browser (Edge/Chrome) could be launched: {last_err}")


def ensure_token(out_path, email, password, gauth="", force=False, show=False, log=print) -> dict:
    """اگر فایل توکن هست و force نیست، همان را برمی‌گرداند؛ وگرنه ورود می‌کند و می‌سازد."""
    out_path = Path(out_path)
    if out_path.exists() and not force:
        try:
            tok = json.loads(out_path.read_text(encoding="utf-8"))
            if tok.get("refresh_token"):
                return tok
        except Exception:
            pass
    tok = login_and_get_token(email, password, gauth, show=show, log=log)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(tok, indent=2), encoding="utf-8")
    return tok


def main():
    ap = argparse.ArgumentParser(description="ورود خودکار مایکروسافت و ساخت فایل توکن xbrp")
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--gauth", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--show", action="store_true", help="مرورگر دیده شود (برای عیب‌یابی)")
    a = ap.parse_args()
    tok = ensure_token(a.out, a.email, a.password, a.gauth, force=a.force, show=a.show)
    print("OK:", a.out, "refresh_token len", len(tok.get("refresh_token", "")))


if __name__ == "__main__":
    main()
