import urllib.request
import urllib.parse
import http.cookiejar
import re
import json
import os
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://mgb2bmall.adminplus.co.kr/partner"
CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT_PATH = os.path.join(CONFIG_DIR, "snapshot_latest.json")
REPORT_PATH = os.path.join(CONFIG_DIR, "report_latest.json")
HISTORY_DIR = os.path.join(CONFIG_DIR, "history")

UA = "Mozilla/5.0"

PRODUCT_PATTERN = re.compile(
    r"prtView\(\"(\d+)\".*?"
    r"float:left;[^>]*>(.*?)</div>.*?"
    r"float:right;[^>]*>(.*?)</div>.*?"
    r"<div class='pname'>(.*?)</div>.*?"
    r"공급가:</th>\s*<td>(.*?)</td>.*?"
    r"배송비:</th>\s*<td>(.*?)</td>",
    re.S,
)


def login(opener, admid, admpwd):
    login_url = f"{BASE}/login.html?rtnurl=%2Fpartner%2F%3Fmod%3Dproduct%26actpage%3Dprt.list"
    req = urllib.request.Request(login_url, headers={"User-Agent": UA})
    opener.open(req).read()

    data = urllib.parse.urlencode({"admid": admid, "admpwd": admpwd, "rejoin": ""}).encode()
    req = urllib.request.Request(
        f"{BASE}/login.chk.php",
        data=data,
        headers={
            "User-Agent": UA,
            "Referer": f"{BASE}/login.html",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    return opener.open(req).read().decode("utf-8").strip()


def fetch_page(opener, page):
    url = f"{BASE}/?mod=product/json&actpage=prt.list.proc&page={page}&order=&by=&searchval="
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return opener.open(req).read().decode("utf-8")


def get_total_pages(xml_text):
    m = re.search(r"<totalpage><!\[CDATA\[(\d+)\]\]></totalpage>", xml_text)
    return int(m.group(1)) if m else 1


def parse_products(xml_text):
    products = {}
    for pcode, cutoff, tax, name, price, shipping in PRODUCT_PATTERN.findall(xml_text):
        products[pcode] = {
            "name": name.strip(),
            "price_raw": price.strip(),
            "shipping": shipping.strip(),
            "cutoff": cutoff.strip(),
            "tax": tax.strip(),
        }
    return products


def main():
    admid = os.environ.get("MGB_ADMID")
    admpwd = os.environ.get("MGB_ADMPWD")
    if not admid or not admpwd:
        print(json.dumps({"error": "MISSING_CREDENTIALS"}, ensure_ascii=False))
        sys.exit(1)

    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    result = login(opener, admid, admpwd)
    if result != "ok":
        print(json.dumps({"error": f"LOGIN_FAILED: {result}"}, ensure_ascii=False))
        sys.exit(1)

    first_page_xml = fetch_page(opener, 1)
    total_pages = get_total_pages(first_page_xml)

    all_products = {}
    all_products.update(parse_products(first_page_xml))
    for page in range(2, total_pages + 1):
        all_products.update(parse_products(fetch_page(opener, page)))

    prev = {}
    if os.path.exists(SNAPSHOT_PATH):
        with open(SNAPSHOT_PATH, encoding="utf-8") as f:
            prev = json.load(f)

    added_codes = sorted(set(all_products) - set(prev))
    removed_codes = sorted(set(prev) - set(all_products))
    changed_codes = [
        pcode
        for pcode in sorted(set(all_products) & set(prev))
        if all_products[pcode]["price_raw"] != prev[pcode]["price_raw"]
    ]

    today = datetime.now().strftime("%Y-%m-%d")

    os.makedirs(HISTORY_DIR, exist_ok=True)
    with open(os.path.join(HISTORY_DIR, f"{today}.json"), "w", encoding="utf-8") as f:
        json.dump(all_products, f, ensure_ascii=False, indent=2)
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_products, f, ensure_ascii=False, indent=2)

    report = {
        "date": today,
        "is_first_run": not prev,
        "total_count": len(all_products),
        "prev_count": len(prev),
        "added": [{"pcode": p, **all_products[p]} for p in added_codes],
        "removed": [{"pcode": p, **prev[p]} for p in removed_codes],
        "changed": [
            {
                "pcode": p,
                "name": all_products[p]["name"],
                "old_price": prev[p]["price_raw"],
                "new_price": all_products[p]["price_raw"],
            }
            for p in changed_codes
        ],
    }

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
