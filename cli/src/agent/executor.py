import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional
from playwright.sync_api import sync_playwright, Page
from rich.console import Console
from agent.logger import EventLogger

console = Console()

EXTRACT_SALES_TABLE_JS = """
() => {
    const rows = document.querySelectorAll('table tbody tr');
    const invoices = [];
    rows.forEach(row => {
        const cells = row.querySelectorAll('td');
        if (cells.length < 6) return;
        const links = row.querySelectorAll('a[href*="/desktop/sale/"]');
        let envoice_id = '';
        for (const link of links) {
            const m = link.href.match(/\\/desktop\\/sale\\/(?:view|edit)\\/(\\d+)/);
            if (m) { envoice_id = m[1]; break; }
        }
        invoices.push({
            envoice_id,
            invoice_date: cells[1]?.textContent.trim() || '',
            customer: cells[3]?.textContent.trim() || '',
            invoice_number: cells[4]?.textContent.trim() || '',
            total: cells[5]?.textContent.trim() || '',
            status: cells[9]?.textContent.trim() || ''
        });
    });
    return invoices;
}
"""

SCAN_EXISTING_DRAFTS_JS = """
() => {
    const rows = document.querySelectorAll('table tbody tr');
    const drafts = [];
    rows.forEach(row => {
        const cells = row.querySelectorAll('td');
        if (cells.length < 6) return;
        const customer = cells[3]?.textContent.trim() || '';
        const dateText = row.innerText;
        const dateMatch = dateText.match(/(\\d{2}\\.\\d{2}\\.\\d{4})/);
        if (customer && dateMatch) {
            drafts.push({ customer: customer.toLowerCase(), date: dateMatch[1] });
        }
    });
    return drafts;
}
"""

JS_FUNCTIONS = {
    "extract_sales_table": EXTRACT_SALES_TABLE_JS,
    "scan_existing_drafts": SCAN_EXISTING_DRAFTS_JS,
}

COOKIE_SELECTORS = [
    "button:has-text('Accept All')",
    "button:has-text('Accept all')",
    "button:has-text('Accept')",
    "button.cky-btn-accept",
    "button[id='cky-btn-accept']",
    "button:has-text('OK')",
    "button:has-text('Agree')",
]


class SkillExecutor:
    def __init__(self, run_id: str, auth_name: str = "envoice"):
        self.run_id = run_id
        self.auth_name = auth_name
        self.artifacts_dir = Path(".state/artifacts") / run_id
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.step_data: Dict[str, Any] = {}
        self._reauth_attempts = 0
        self._max_reauth_attempts = 1
        self.report = {
            "run_id": run_id,
            "status": "running",
            "steps_completed": 0,
            "steps_total": 0,
            "artifacts": {},
            "extracted_data": {},
        }

    def log_action(self, action: str, details: str):
        EventLogger.console_log("Executor", f"[bold]{action}[/bold] {details}")
        EventLogger.log("agent_action", f"{action} {details}", {"run_id": self.run_id})

    def _persist_report(self) -> Dict[str, Any]:
        report_path = self.artifacts_dir / "run_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(self.report, f, indent=2)
        self.report["artifacts"]["run_report_json"] = str(report_path)
        return self.report

    def _resolve_value(self, value: Optional[str], slots: Dict[str, Any]) -> str:
        if not value or not isinstance(value, str):
            return value or ""
        for k, v in slots.items():
            value = value.replace(f"{{{{{k}}}}}", str(v))
        # If any {{placeholder}} remains unresolved, return empty string
        if re.search(r"\{\{.+?\}\}", value):
            self.log_action("skip", f"unresolved placeholder in '{value}'")
            return ""
        return value

    def _is_login_page(self, page: Page) -> bool:
        url = (page.url or "").lower()
        if any(token in url for token in ["/login", "/signin", "/sign-in", "/auth"]):
            return True

        try:
            password_visible = page.locator("input[type='password']").first.is_visible(
                timeout=500
            )
            identity_visible = page.locator(
                "input[type='email'], input[name*='email'], input[id*='email'], "
                "input[name*='user'], input[id*='user']"
            ).first.is_visible(timeout=500)
            return bool(password_visible and identity_visible)
        except Exception:
            return False

    def _fill_first_visible(self, page: Page, selectors: list[str], value: str) -> bool:
        for selector in selectors:
            try:
                field = page.locator(selector).first
                if field.is_visible(timeout=500):
                    field.fill(value)
                    return True
            except Exception:
                continue
        return False

    def _auto_relogin_if_needed(
        self,
        page: Page,
        context,
        auth_path: Path,
        resume_url: Optional[str] = None,
    ) -> bool:
        if not self._is_login_page(page):
            return False

        if self._reauth_attempts >= self._max_reauth_attempts:
            self.log_action("auth", "session expired and max relogin attempts reached")
            return False

        username = os.getenv("ENVOICE_USERNAME")
        password = os.getenv("ENVOICE_PASSWORD")
        if not username or not password:
            self.log_action(
                "auth",
                "session expired but ENVOICE_USERNAME/ENVOICE_PASSWORD not configured",
            )
            return False

        self._reauth_attempts += 1
        self.log_action("auth", "session expired, attempting automatic login")

        email_ok = self._fill_first_visible(
            page,
            [
                "input[type='email']",
                "input[name='email']",
                "input[id='email']",
                "input[name*='user']",
                "input[id*='user']",
            ],
            username,
        )
        password_ok = self._fill_first_visible(
            page,
            [
                "input[type='password']",
                "input[name='password']",
                "input[id='password']",
            ],
            password,
        )

        if not (email_ok and password_ok):
            self.log_action("auth", "auto-login fields not found")
            return False

        clicked = False
        for selector in [
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Sign in')",
            "button:has-text('Log in')",
            "button:has-text('Login')",
        ]:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=500):
                    btn.click()
                    clicked = True
                    break
            except Exception:
                continue

        if not clicked:
            try:
                page.keyboard.press("Enter")
                clicked = True
            except Exception:
                pass

        if not clicked:
            self.log_action("auth", "auto-login submit action failed")
            return False

        try:
            page.wait_for_timeout(2000)
            page.wait_for_url(
                lambda url: (
                    not any(
                        token in (url or "").lower()
                        for token in ["/login", "/signin", "/sign-in", "/auth"]
                    )
                ),
                timeout=30000,
            )
        except Exception:
            if self._is_login_page(page):
                self.log_action("auth", "auto-login did not leave login page")
                return False

        if resume_url:
            try:
                page.goto(resume_url, wait_until="networkidle", timeout=30000)
            except Exception:
                pass

        try:
            auth_path.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(auth_path))
            self.log_action("auth", f"auth state refreshed at {auth_path}")
        except Exception as e:
            self.log_action("warning", f"failed to refresh auth state: {e}")

        return True

    def _dismiss_modals(self, page: Page):
        """Dismiss any blocking modals (e.g. companyAddModal) before proceeding."""
        try:
            modal = page.locator(
                "#companyAddModal.modal.in, #companyAddModal.modal.show"
            ).first
            if modal.is_visible(timeout=500):
                # Try closing via the X button or Cancel
                for close_sel in [
                    "#companyAddModal .close",
                    "#companyAddModal button:has-text('Close')",
                    "#companyAddModal button:has-text('Cancel')",
                    "#companyAddModal [data-dismiss='modal']",
                ]:
                    try:
                        btn = page.locator(close_sel).first
                        if btn.is_visible(timeout=500):
                            btn.click(force=True)
                            page.wait_for_timeout(1000)
                            self.log_action(
                                "dismissed", "blocking modal via close button"
                            )
                            return
                    except Exception:
                        continue
                # Fallback: hide via JS
                page.evaluate("""
                    document.querySelector('#companyAddModal')?.classList.remove('in','show');
                    document.querySelector('#companyAddModal')?.style.setProperty('display','none');
                    document.querySelector('.modal-backdrop')?.remove();
                    document.body.classList.remove('modal-open');
                    document.body.style.removeProperty('padding-right');
                """)
                page.wait_for_timeout(500)
                self.log_action("dismissed", "blocking modal via JS fallback")
        except Exception:
            pass

    def _handle_cookies(self, page: Page):
        """Dismiss cookie consent banners using production-tested selectors."""
        self.log_action("handling", "cookie consent banner")
        for selector in COOKIE_SELECTORS:
            try:
                el = page.locator(selector).first
                if el.is_visible(timeout=2000):
                    el.click()
                    page.wait_for_timeout(1500)
                    self.log_action("dismissed", "cookie banner")
                    return
            except Exception:
                continue
        # Try hiding overlay directly
        try:
            page.evaluate("document.querySelector('.cky-overlay')?.remove()")
        except Exception:
            pass
        self.log_action("skipped", "no cookie banner found")

    def _select2(self, page: Page, step: Dict[str, Any], value: str):
        """Handle Select2 dropdown: click container, type search, pick result."""
        if not value:
            self.log_action("skip", "select2 with empty value")
            return

        self._dismiss_modals(page)

        selector = step.get("selector", "")
        search_sel = step.get("search", "input.select2-search__field")
        result_sel = step.get("result", ".select2-results__option")

        self.log_action("select2", f"searching '{value}' in '{selector}'")

        try:
            page.click(selector, timeout=8000)
        except Exception:
            # JS click fallback
            try:
                el = page.query_selector(selector)
                if el:
                    page.evaluate("el => el.click()", el)
            except Exception as e:
                self.log_action("warning", f"select2 container click failed: {e}")
                return

        page.wait_for_timeout(500)

        try:
            search_field = page.locator(search_sel).last
            search_field.wait_for(state="visible", timeout=5000)
            search_field.fill(value)
        except Exception as e:
            self.log_action("warning", f"select2 search field not found: {e}")
            return

        page.wait_for_timeout(2000)

        try:
            # Try clicking highlighted first, then first visible result
            highlighted = page.locator(".select2-results__option--highlighted").first
            if highlighted.is_visible(timeout=2000):
                highlighted.click()
                self.log_action("selected", f"highlighted option for '{value}'")
                return
        except Exception:
            pass

        try:
            results = page.locator(result_sel)
            count = results.count()
            for i in range(count):
                option = results.nth(i)
                text = option.text_content() or ""
                if value.lower() in text.lower():
                    option.click()
                    self.log_action("selected", f"option '{text.strip()}'")
                    return
            # Fallback: press Enter
            page.keyboard.press("Enter")
            self.log_action("selected", f"via Enter key for '{value}'")
        except Exception as e:
            page.keyboard.press("Enter")
            self.log_action("fallback", f"Enter key after select2 error: {e}")

    def _select2_tax(self, page: Page, step: Dict[str, Any], value: str):
        """Handle tax rule Select2 with sibling container pattern."""
        if not value:
            self.log_action("skip", "select2_tax with empty value")
            return
        self._dismiss_modals(page)
        select_name = step.get("selector", "")
        self.log_action("select2_tax", f"setting tax rule to '{value}'")

        try:
            container = page.locator(
                "xpath=//select[contains(@name, 'vat_rate_chart_of_accounts_id')]"
                "/following-sibling::span[contains(@class, 'select2-container')]"
            ).first
            if container.is_visible(timeout=5000):
                container.click()
                page.wait_for_timeout(500)
                search = page.locator("input.select2-search__field").last
                search.fill(value)
                page.wait_for_timeout(1500)
                page.locator(".select2-results__option--highlighted").first.click()
                self.log_action("selected", f"tax rule '{value}' via Select2")
                return
        except Exception:
            pass

        # Fallback: scan native <select> options
        try:
            options = page.locator(f"{select_name} option").all_inner_texts()
            match = next((o for o in options if value.lower() in o.lower()), None)
            if match:
                page.select_option(select_name, label=match)
                self.log_action("selected", f"tax rule '{match}' via native select")
            else:
                self.log_action("warning", f"no tax option matching '{value}'")
        except Exception as e:
            self.log_action("error", f"tax rule selection failed: {e}")

    def _fill_date(self, page: Page, selector: str, value: str):
        """Fill a date field robustly using click+type+Tab+JS evaluation."""
        if not value:
            self.log_action("skip", "date fill with empty value")
            return
        self._dismiss_modals(page)
        self.log_action("filling date", f"'{selector}' with '{value}'")
        try:
            page.click(selector, timeout=5000)
            page.fill(selector, "")
            page.type(selector, value)
            page.keyboard.press("Tab")
            # Belt-and-suspenders: also set via JS
            page.evaluate(f'document.querySelector("{selector}").value = "{value}"')
        except Exception as e:
            self.log_action("warning", f"date fill fallback: {e}")
            try:
                page.fill(selector, value)
            except Exception:
                pass

    def _check_validation(self, page: Page):
        """Check for Envoice validation errors and log them."""
        try:
            errors = page.locator(
                ".popover-content:has-text('Mandatory'), "
                ".help-block:has-text('Mandatory'), "
                ".text-danger:has-text('Mandatory')"
            )
            count = errors.count()
            if count > 0:
                texts = [errors.nth(i).text_content() for i in range(min(count, 5))]
                self.log_action("validation_error", f"{count} errors: {texts}")
                self.report["validation_errors"] = texts
            else:
                self.log_action("validation", "no errors detected")
        except Exception:
            pass

    def _apply_slot_defaults(self, slots: Dict[str, Any]) -> Dict[str, Any]:
        """Fill missing slots with sensible defaults so placeholders don't leak."""
        today = datetime.now()
        defaults = {
            "invoice_date": today.strftime("%d.%m.%Y"),
            "payment_deadline": (today + timedelta(days=14)).strftime("%d.%m.%Y"),
            "due_date": (today + timedelta(days=14)).strftime("%d.%m.%Y"),
            "delivery_date": today.strftime("%d.%m.%Y"),
            "currency": "EUR",
            "quantity": "1",
            "unit": "month",
            "description": "General Service",
            "tax_rule": "Service export",
        }
        merged = {**defaults, **{k: v for k, v in slots.items() if v}}
        return merged

    def execute(
        self, skill_spec: Dict[str, Any], slots: Dict[str, Any]
    ) -> Dict[str, Any]:
        slots = self._apply_slot_defaults(slots)
        steps = skill_spec.get("steps", [])
        self.report["steps_total"] = len(steps)
        self.report["skill_id"] = skill_spec.get("id", "unknown")
        self.report["skill_version"] = skill_spec.get("version", 0)

        auth_path = Path(".state/auth") / f"{self.auth_name}.json"
        browser = None
        context = None
        page = None
        trace_started = False

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=os.getenv("HEADLESS", "1") == "1")

                context_kwargs = {
                    "record_video_dir": str(self.artifacts_dir),
                    "viewport": {"width": 1920, "height": 1080},
                    "user_agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/122.0.0.0 Safari/537.36"
                    ),
                }
                if auth_path.exists():
                    context_kwargs["storage_state"] = str(auth_path)
                    self.log_action("loading", f"auth session from {auth_path}")
                else:
                    self.log_action(
                        "warning", "no auth session found, proceeding without login"
                    )

                context = browser.new_context(**context_kwargs)
                context.tracing.start(screenshots=True, snapshots=True, sources=True)
                trace_started = True

                page = context.new_page()
                step_index = 0

                for i, step in enumerate(steps):
                    action = step.get("action")
                    selector = step.get("selector")
                    value = self._resolve_value(step.get("value"), slots)

                    if action != "goto":
                        self._auto_relogin_if_needed(page, context, auth_path)

                    if action == "handle_cookies":
                        self._handle_cookies(page)

                    elif action == "goto":
                        self.log_action("navigating", f"to {value}")
                        page.goto(value, wait_until="networkidle", timeout=30000)
                        self._auto_relogin_if_needed(
                            page, context, auth_path, resume_url=value
                        )

                    elif action == "click":
                        self._dismiss_modals(page)
                        self.log_action("clicking", f"'{selector}'")
                        try:
                            page.click(selector, timeout=8000)
                        except Exception:
                            el = page.query_selector(selector)
                            if el:
                                page.evaluate("el => el.click()", el)
                            else:
                                raise

                    elif action == "fill":
                        resolved_val = self._resolve_value(value, slots)
                        if not resolved_val:
                            self.log_action("skip", f"fill '{selector}' — empty value")
                        else:
                            self._dismiss_modals(page)
                            self.log_action(
                                "filling", f"'{selector}' → '{resolved_val}'"
                            )
                            page.fill(selector, resolved_val, timeout=8000)

                    elif action == "fill_if_visible":
                        resolved_val = self._resolve_value(value, slots)
                        if resolved_val:
                            try:
                                el = page.locator(selector).first
                                if el.is_visible(timeout=3000):
                                    el.fill(resolved_val)
                                    self.log_action(
                                        "filled", f"'{selector}' → '{resolved_val}'"
                                    )
                            except Exception:
                                pass

                    elif action == "fill_date":
                        self._fill_date(page, selector, value)

                    elif action == "select2":
                        self._select2(page, step, value)

                    elif action == "select2_tax":
                        self._select2_tax(page, step, value)

                    elif action == "select_option":
                        if not value:
                            self.log_action(
                                "skip", f"select_option '{selector}' — empty value"
                            )
                            self.report["steps_completed"] += 1
                            continue
                        self._dismiss_modals(page)
                        self.log_action(
                            "selecting", f"option '{value}' in '{selector}'"
                        )
                        try:
                            page.select_option(selector, label=value, timeout=5000)
                        except Exception:
                            try:
                                page.select_option(selector, value=value, timeout=3000)
                            except Exception as e:
                                self.log_action(
                                    "warning", f"select_option fallback: {e}"
                                )

                    elif action == "wait":
                        if selector:
                            timeout = int(step.get("timeout", 10000))
                            self.log_action("waiting", f"for '{selector}'")
                            page.wait_for_selector(selector, timeout=timeout)
                        else:
                            ms = int(value or 1000)
                            self.log_action("waiting", f"{ms}ms")
                            page.wait_for_timeout(ms)

                    elif action == "wait_for_url":
                        timeout = int(step.get("timeout", 15000))
                        patterns = [p.strip() for p in value.split("|")]
                        self.log_action("waiting", f"for URL matching {patterns}")
                        page.wait_for_url(
                            lambda url: any(
                                re.search(
                                    pat.replace("**", ".*").replace("*", "[^/]*"),
                                    url,
                                )
                                for pat in patterns
                            ),
                            timeout=timeout,
                        )

                    elif action == "evaluate":
                        fn_name = value
                        store_as = step.get("store_as", fn_name)
                        js_fn = JS_FUNCTIONS.get(fn_name, f"() => {{ {value} }}")
                        self.log_action("evaluating", f"JS function '{fn_name}'")
                        result = page.evaluate(js_fn)
                        self.step_data[store_as] = result
                        self.report["extracted_data"][store_as] = result

                    elif action == "check_validation":
                        self._check_validation(page)

                    elif action == "screenshot":
                        step_index += 1
                        path = self.artifacts_dir / f"step_{step_index}.png"
                        page.screenshot(path=str(path))
                        self.report["artifacts"][f"step_{step_index}_png"] = str(path)
                        self.log_action("screenshot", f"saved step_{step_index}.png")

                    elif action == "foreach":
                        self.log_action(
                            "info", "foreach is handled by the orchestrator"
                        )

                    else:
                        self.log_action(
                            "warning", f"unknown action '{action}', skipping"
                        )

                    self.report["steps_completed"] += 1

                # Final screenshot
                last_png = self.artifacts_dir / "last.png"
                page.screenshot(path=str(last_png))
                self.report["artifacts"]["last_png"] = str(last_png)

                # Capture final URL
                self.report["final_url"] = page.url
                invoice_match = re.search(r"(?:/edit/(\d+)|[?&]id=(\d+))", page.url)
                if invoice_match:
                    created_invoice_id = invoice_match.group(1) or invoice_match.group(2)
                    self.report["created_invoice_id"] = created_invoice_id
                    self.log_action(
                        "success",
                        f"invoice created with ID {created_invoice_id}",
                    )

                validation_errors = self.report.get("validation_errors") or []
                skill_id = str(skill_spec.get("id") or "")
                expects_invoice_id = (
                    "invoice" in skill_id
                    and "extract" not in skill_id
                    and "bulk" not in skill_id
                )
                created_invoice_id = self.report.get("created_invoice_id")

                if validation_errors:
                    self.report["status"] = "failed"
                    self.report["error"] = (
                        f"Validation errors detected: {len(validation_errors)}"
                    )
                    self.report["failure_class"] = "validation_error"
                    self.log_action(
                        "error", "validation errors detected; marking run as failed"
                    )
                elif expects_invoice_id and not created_invoice_id:
                    self.report["status"] = "failed"
                    self.report["error"] = (
                        "Invoice creation flow ended without a created invoice id."
                    )
                    self.report["failure_class"] = "missing_created_record"
                    self.log_action(
                        "error",
                        "no created invoice id found in final URL; marking run as failed",
                    )
                else:
                    self.report["status"] = "success"
                    self.log_action("finished", "workflow completed successfully")

        except Exception as e:
            error_text = str(e).strip()
            error_summary = (
                error_text.splitlines()[0] if error_text else type(e).__name__
            )
            self.log_action("error", f"encountered: {error_summary}")
            self.report["status"] = "failed"
            self.report["error"] = error_summary
            self.report["error_details"] = error_text
            if page is not None:
                try:
                    error_png = self.artifacts_dir / "error.png"
                    page.screenshot(path=str(error_png))
                    self.report["artifacts"]["last_png"] = str(error_png)
                except Exception:
                    pass
        finally:
            self.log_action("saving", "trace and video artifacts")
            if trace_started and context is not None:
                try:
                    trace_path = self.artifacts_dir / "trace.zip"
                    context.tracing.stop(path=str(trace_path))
                    self.report["artifacts"]["trace_zip"] = str(trace_path)
                except Exception:
                    pass

            if page is not None:
                try:
                    video = page.video
                    if video:
                        video_path = video.path()
                        final_video_path = self.artifacts_dir / "video.webm"
                        os.rename(video_path, final_video_path)
                        self.report["artifacts"]["video_webm"] = str(final_video_path)
                except Exception:
                    pass

            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass

            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass

        return self._persist_report()
