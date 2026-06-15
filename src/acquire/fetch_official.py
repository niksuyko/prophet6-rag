"""Download official Sequential Prophet-6 documentation into data/raw/official/.

URLs verified live 2026-06-11. Zendesk KB pages need a browser User-Agent (403 otherwise).
"""
from util import RAW_DIR, polite_get, record, session

DOCS = [
    # (url, filename, note)
    ("https://sequential.com/wp-content/uploads/2021/02/Prophet-6-Operation-Manual-2.1.pdf",
     "prophet6_operation_manual_2.1.pdf", "operation manual v2.1"),
    ("https://sequential.com/wp-content/uploads/2022/02/Prophet-6-Manual-Addendum-OS-v1.6.7.pdf",
     "prophet6_addendum_os_1.6.7.pdf", "OS 1.6.7 addendum (MPE, vintage mode)"),
    ("https://www.davesmithinstruments.com/wp-content/uploads/2016/05/Prophet-6-OS-1.3.1-Addendum.pdf",
     "prophet6_addendum_os_1.3.1.pdf", "OS 1.3.1 addendum"),
    ("https://sequential.com/wp-content/uploads/2021/12/Prophet-6_OS-1.7.5ReadMe.zip",
     "prophet6_os_1.7.5_readme.zip", "current OS package incl. release-notes ReadMe"),
    ("https://sequential.com/updating-the-prophet-6-os/",
     "prophet6_os_update_instructions.html", "official OS update walkthrough"),
    ("https://support.sequential.com/hc/en-gb/articles/5315353892242-Prophet-6-Keyboard-Troubleshooting",
     "prophet6_kb_keyboard_troubleshooting.html", "official KB: keyboard troubleshooting/calibration"),
    ("https://support.sequential.com/hc/en-gb/articles/5315364186386-Prophet-6-Module-Troubleshooting",
     "prophet6_kb_module_troubleshooting.html", "official KB: desktop module troubleshooting"),
]


def main() -> None:
    out_dir = RAW_DIR / "official"
    out_dir.mkdir(parents=True, exist_ok=True)
    sess = session()
    for url, filename, note in DOCS:
        dest = out_dir / filename
        if dest.exists():
            print(f"skip (exists): {filename}")
            continue
        resp = polite_get(sess, url)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        record(f"official/{filename}", url, note=note)
        print(f"saved: {filename} ({len(resp.content)} bytes)")


if __name__ == "__main__":
    main()
