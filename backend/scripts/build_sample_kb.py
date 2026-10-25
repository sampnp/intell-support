"""Generate the Acme Cloud sample PDFs and the binary malformed fixtures (docs/PLAN.md §10).

Run inside the backend container (sample_kb/ is mounted at $SAMPLE_KB_DIR):

    docker compose run --rm backend python scripts/build_sample_kb.py

The output is committed. The TXT documents, malformed/empty.txt and malformed/not-really.pdf
are written by hand and are not touched by this script. Output is reproducible: fixed creation
date, fixed random seed.
"""

import os
import random
from datetime import UTC, datetime
from pathlib import Path

from fpdf import FPDF

OUT_DIR = Path(os.environ.get("SAMPLE_KB_DIR", "/sample_kb"))
FIXED_DATE = datetime(2026, 1, 1, tzinfo=UTC)

# Each document: title, then pages; each page is a list of (heading, paragraphs).
# Plain ASCII only: the built-in PDF fonts are Latin-1.
GETTING_STARTED = (
    "Acme Cloud - Getting Started Guide",
    [
        [
            (
                "1. Creating your account",
                [
                    "Welcome to Acme Cloud, the simple way to store, sync and share your files. "
                    "To create an account, go to acmecloud.example and choose Sign up. Enter "
                    "your name, your email address and a password of at least 10 characters.",
                    "We send a verification email to the address you entered. Click the link in "
                    "that email within 24 hours to activate your account. Until the address is "
                    "verified you can upload files, but you cannot share them with other people.",
                    "New accounts start on the Free plan with 5 GB of storage. You can upgrade to "
                    "Personal or Business at any time from Settings > Plan without losing any files.",
                ],
            ),
            (
                "2. Setting up your profile",
                [
                    "Open Settings > Profile to add a profile photo and choose your language and "
                    "time zone. The time zone is used for file timestamps and activity emails.",
                    "We strongly recommend turning on two-factor authentication in "
                    "Settings > Security before you store anything important. It takes two "
                    "minutes with any authenticator app.",
                ],
            ),
        ],
        [
            (
                "3. Installing the desktop app",
                [
                    "The Acme Cloud desktop app is available for Windows 10 and later and for "
                    "macOS 12 and later. Download it from acmecloud.example/download and run the "
                    "installer. You do not need administrator rights for a per-user installation.",
                    "After installation, sign in with your Acme Cloud account. The app creates an "
                    "Acme Cloud folder in your home directory. You can choose a different "
                    "location during setup, for example a second drive with more free space.",
                    "The desktop app starts automatically when you log in to your computer and "
                    "runs in the system tray on Windows or the menu bar on macOS.",
                ],
            ),
            (
                "4. Installing the mobile apps",
                [
                    "The Acme Cloud mobile app is available for iPhone and iPad from the App Store "
                    "and for Android phones from Google Play. Sign in with the same account you "
                    "use on your computer.",
                    "The mobile app does not download all of your files. It shows everything in "
                    "your cloud storage and downloads a file only when you open it. Mark files as "
                    "available offline to keep a copy on the device.",
                    "Camera upload can automatically back up the photos and videos you take. "
                    "Turn it on in the app settings and choose whether uploads may use mobile "
                    "data or only Wi-Fi.",
                ],
            ),
        ],
        [
            (
                "5. Your first sync",
                [
                    "To add files to Acme Cloud, drag them into the Acme Cloud folder on your "
                    "computer. The desktop app uploads them in the background and the tray icon "
                    "shows blue arrows while syncing is in progress.",
                    "When the icon shows a green tick, your files are safely stored in the cloud "
                    "and are available on the web and on every device where you are signed in. "
                    "Changes you make on one device appear on the others within a few seconds.",
                    "The first sync of a large folder can take a while, depending on your upload "
                    "speed. You can keep working while it runs; pausing and resuming is safe.",
                ],
            ),
            (
                "6. Where to get help",
                [
                    "If something does not work as expected, open the help center at "
                    "acmecloud.example/help or create a support ticket from the web app. Include "
                    "the version of the app you use and a description of what you tried.",
                ],
            ),
        ],
    ],
)

BILLING_REFUND = (
    "Acme Cloud - Billing and Refund Policy",
    [
        [
            (
                "1. Plans and pricing",
                [
                    "Acme Cloud offers three plans. Free includes 5 GB of storage. Personal costs "
                    "9.99 USD per month or 99 USD per year and includes 2 TB. Business costs "
                    "15 USD per user per month, billed annually, and includes 5 TB per user plus "
                    "admin controls.",
                    "Annual plans are paid in advance for twelve months. Monthly plans renew "
                    "automatically on the same day each month until you cancel.",
                ],
            ),
            (
                "2. Invoices and receipts",
                [
                    "We email a receipt after every successful payment. All invoices are also "
                    "available in Settings > Billing > Invoices, where you can download them as "
                    "PDF files.",
                    "Business customers can add a company name, billing address and VAT number in "
                    "Settings > Billing. These details appear on all future invoices; past "
                    "invoices cannot be reissued with new details.",
                ],
            ),
            (
                "3. Payment failures",
                [
                    "If a renewal payment fails, for example because a card has expired or was "
                    "declined by the bank, we retry the payment three times over seven days and "
                    "email you after each attempt.",
                    "To fix a failed payment, update your card in Settings > Billing > Payment "
                    "method. The outstanding amount is charged immediately after you save a new "
                    "card. If all retries fail, the account is moved to the Free plan. Files are "
                    "never deleted because of a failed payment, but syncing stops if you are over "
                    "the Free storage quota.",
                ],
            ),
        ],
        [
            (
                "4. Refunds",
                [
                    "You can request a full refund within 14 days of your first purchase of a "
                    "Personal or Business plan. After 14 days, payments are not refundable, "
                    "except where local consumer law requires otherwise.",
                    "Annual renewals can be refunded if you request it within 7 days of the "
                    "renewal date and have not uploaded files since the renewal. Monthly renewals "
                    "are not refunded.",
                    "If you were charged twice for the same period, contact support with both "
                    "receipt numbers. Duplicate charges are always refunded in full, usually "
                    "within 5 to 10 business days depending on your bank.",
                    "Refunds go back to the original payment method. We cannot refund to a "
                    "different card or as account credit.",
                ],
            ),
            (
                "5. Cancelling your subscription",
                [
                    "Cancel at any time in Settings > Billing > Cancel subscription. Your paid "
                    "plan stays active until the end of the period you already paid for, and then "
                    "the account moves to the Free plan.",
                    "Cancelling does not delete any files. If you store more than 5 GB when the "
                    "account moves to Free, your files remain available to view and download, "
                    "but new uploads are blocked until you are under the quota.",
                ],
            ),
        ],
    ],
)

SHARING_FAQ = (
    "Acme Cloud - Sharing and Permissions FAQ",
    [
        [
            (
                "How do I share a file or folder with a link?",
                [
                    "Right-click a file or folder in the web app or the desktop app and choose "
                    "Share > Copy link. Anyone who has the link can view the content. They do not "
                    "need an Acme Cloud account.",
                    "Links to folders show the current contents of the folder, including files "
                    "added after the link was created.",
                ],
            ),
            (
                "Can I make a share link expire or add a password?",
                [
                    "Yes, on Personal and Business plans. In the link settings, set an expiry "
                    "date after which the link stops working, and optionally a password that "
                    "people must enter before they can open the content.",
                    "Expired links show the message This link has expired. You can extend the "
                    "expiry date at any time and the same link starts working again.",
                ],
            ),
            (
                "How do I stop sharing?",
                [
                    "Open the share dialog and choose Delete link. Anyone who tries to use the "
                    "link afterwards sees an error. People who already downloaded a copy keep "
                    "that copy.",
                ],
            ),
        ],
        [
            (
                "What are the access levels?",
                [
                    "When you invite people by email you choose an access level. Viewers can open "
                    "and download files. Commenters can also add comments. Editors can change, "
                    "upload and delete files in the shared folder. Only the owner can delete the "
                    "folder itself or change who has access.",
                ],
            ),
            (
                "What is a team folder?",
                [
                    "Team folders are available on the Business plan. They belong to the "
                    "workspace instead of to one person, so files stay available when someone "
                    "leaves the company. Workspace administrators decide which groups can access "
                    "each team folder.",
                    "Files in team folders count towards the workspace storage, not the "
                    "personal quota of the people who uploaded them.",
                ],
            ),
            (
                "Why can't I share outside my company?",
                [
                    "Business administrators can restrict sharing so that links only work for "
                    "people in the workspace, or block external sharing completely. If the share "
                    "button is disabled, ask your administrator to review the sharing policy.",
                ],
            ),
        ],
    ],
)


def new_pdf(title: str) -> FPDF:
    pdf = FPDF(format="A4")
    pdf.creation_date = FIXED_DATE
    pdf.set_title(title)
    pdf.set_author("Acme Cloud Support")
    pdf.set_auto_page_break(auto=True, margin=15)
    return pdf


def build_document(path: Path, title: str, pages: list) -> None:
    pdf = new_pdf(title)
    for page_number, sections in enumerate(pages):
        pdf.add_page()
        if page_number == 0:
            pdf.set_font("Helvetica", "B", 18)
            pdf.multi_cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(4)
        for heading, paragraphs in sections:
            pdf.set_font("Helvetica", "B", 13)
            pdf.multi_cell(0, 8, heading, new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", size=11)
            for paragraph in paragraphs:
                pdf.multi_cell(0, 6, paragraph, new_x="LMARGIN", new_y="NEXT")
                pdf.ln(3)
            pdf.ln(2)
    pdf.output(str(path))


def build_image_only(path: Path) -> None:
    """A page of drawn shapes only: no text layer, like a scanned document."""
    pdf = new_pdf("Scanned page")
    pdf.add_page()
    pdf.set_fill_color(220, 220, 220)
    pdf.rect(20, 20, 170, 250, style="F")
    pdf.set_draw_color(80, 80, 80)
    for y in range(40, 260, 12):
        pdf.line(30, y, 180, y)
    pdf.output(str(path))


def build_corrupt_pdf(path: Path) -> None:
    """Starts like a PDF (passes the %PDF check) but has no objects, xref or trailer."""
    junk = random.Random(5).randbytes(4096)
    path.write_bytes(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n" + junk)


def build_binary_garbage(path: Path) -> None:
    data = b"\xc3\x28\xa0\xa1" + random.Random(7).randbytes(2048)
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        path.write_bytes(data)
        return
    raise RuntimeError("binary-garbage.txt must not be valid UTF-8")


def main() -> None:
    malformed = OUT_DIR / "malformed"
    malformed.mkdir(parents=True, exist_ok=True)

    outputs = {
        OUT_DIR / "getting-started-guide.pdf": lambda p: build_document(p, *GETTING_STARTED),
        OUT_DIR / "billing-refund-policy.pdf": lambda p: build_document(p, *BILLING_REFUND),
        OUT_DIR / "sharing-permissions-faq.pdf": lambda p: build_document(p, *SHARING_FAQ),
        malformed / "image-only.pdf": build_image_only,
        malformed / "corrupt.pdf": build_corrupt_pdf,
        malformed / "binary-garbage.txt": build_binary_garbage,
    }
    for path, build in outputs.items():
        build(path)
        print(f"wrote {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
