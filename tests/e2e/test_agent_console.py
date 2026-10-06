"""End-to-end tests of the agent console with Playwright (run: pytest tests/e2e)."""
from playwright.sync_api import Page, expect


def analyse(page: Page, url: str, text: str):
    page.goto(url)
    page.fill("#message", text)
    page.click("#analyze")
    expect(page.locator("#intent-name")).not_to_be_empty()


def test_fraud_message_shows_escalation_banner(page: Page, server_url):
    analyse(page, server_url, "Someone used my card 4000 1234 5678 9010 for shopping I did not make")
    expect(page.locator("#alarm")).to_be_visible()
    expect(page.locator("#alarm-title")).to_contain_text("Fraud response team")
    expect(page.locator("#intent-name")).to_have_text("Suspected fraud")
    expect(page.locator("#masked")).to_contain_text("XXXX XXXX XXXX 9010")


def test_tone_switch_keeps_guidance(page: Page, server_url):
    analyse(page, server_url, "I need my bank statement for the last 6 months as a PDF.")
    expect(page.locator("#alarm")).to_be_hidden()
    page.click("[data-tone=empathetic]")
    expect(page.locator("#draft")).to_have_value(__import__("re").compile("12 months"))
    page.click("[data-tone=concise]")
    expect(page.locator("#draft")).to_have_value(__import__("re").compile("12 months"))


def test_edit_save_and_see_in_history(page: Page, server_url):
    analyse(page, server_url, "How can I change my address? I shifted to Madurai.")
    page.fill("#draft", page.input_value("#draft") + "\nAgent added: branch visit also works.")
    page.click("#save")
    expect(page.locator("#summary")).to_contain_text("address update")
    expect(page.locator("#summary")).to_contain_text("edited by agent")
    page.click("#tab-history")
    expect(page.locator("#history article").first).to_contain_text("Address update")


def test_out_of_scope_and_feedback(page: Page, server_url):
    analyse(page, server_url, "What is my account balance?")
    expect(page.locator("#intent-name")).to_have_text("Out of scope")
    expect(page.locator("#nomatch")).to_be_visible()


def test_verification_tab_reports_accuracy(page: Page, server_url):
    page.goto(server_url)
    page.click("#tab-verify")
    page.click("#run-eval")
    expect(page.locator("#eval-table")).to_be_visible()
    expect(page.locator("#metrics .stat").first).to_contain_text("%")


def test_compliance_check_flags_unsafe_edit(page: Page, server_url):
    analyse(page, server_url, "UPI failed but money debited yesterday")
    expect(page.locator("#compliance")).to_have_class(__import__("re").compile("pass"))
    page.fill("#draft", "Please share your OTP and we will refund it in 2 hours.")
    expect(page.locator("#compliance")).to_have_class(__import__("re").compile("block"))
    expect(page.locator("#compliance")).to_contain_text("OTP")
    page.click("#save")
    expect(page.locator("#save")).to_have_text("Save anyway (flags recorded)")
    page.click("#save")
    expect(page.locator("#summary")).to_contain_text("Compliance flags recorded")


def test_multi_issue_and_csv_export(page: Page, server_url):
    analyse(page, server_url, "My UPI transfer failed and money was debited, also I need my bank statement for 6 months")
    expect(page.locator("#also")).to_contain_text("Statement request")
    page.click("#save")
    expect(page.locator("#summary")).to_be_visible()
    res = page.request.get(f"{server_url}/api/interactions.csv")
    assert res.ok and "intent_label" in res.text() and "Failed or pending transfer" in res.text()
