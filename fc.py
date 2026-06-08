import json
import csv
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
    StaleElementReferenceException,
)
from bs4 import BeautifulSoup
import time
from datetime import datetime

# Utility functions

def load_json(file_path):
    try:
        with open(file_path, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        print(f"Error: File {file_path} not found.")
        return []
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON format in {file_path}.")
        return []

def load_csv(file_path):
    try:
        with open(file_path, "r") as file:
            reader = csv.DictReader(file)
            return list(reader)
    except FileNotFoundError:
        print(f"Error: File {file_path} not found.")
        return []

def save_csv(data, file_path, fieldnames):
    """Save data to a CSV file."""
    try:
        with open(file_path, "w", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        print(f"Data successfully exported to {file_path}")
    except Exception as e:
        print(f"Error exporting data to CSV: {e}")

def write_leaderboard(cleared, non_cleared, file_path):
    try:
        with open(file_path, "w") as file:
            file.write("# DMU Progress leaderboard\n\n")

            # Cleared section
            file.write("# Cleared!\n")
            for idx, entry in enumerate(cleared, start=1):
                file.write(f"{idx}. {entry['name']} - {entry['discord']}\n")

            file.write("\n# Proggin'\n")
            for idx, entry in enumerate(non_cleared, start=1):
                pulls = entry.get("pulls", "N/A")
                pull_str = f" ({pulls} pulls)" if pulls not in ("N/A", "", None) else ""
                file.write(f"{idx}. {entry['name']} - {entry['status']}{pull_str}\n")

        print(f"Leaderboard successfully written to {file_path}")
    except Exception as e:
        print(f"Error writing leaderboard: {e}")

# Selenium functionality

# A realistic, current desktop Chrome UA so the request blends in with normal traffic.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def build_driver():
    """Create a Chrome driver tuned to look less like an automated client."""
    options = webdriver.ChromeOptions()

    # Hide the most obvious "I'm a bot" signals.
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option("useAutomationExtension", False)

    # Look like a normal, fully featured browser window.
    options.add_argument(f"--user-agent={USER_AGENT}")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--start-maximized")
    options.add_argument("--lang=en-US,en")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-notifications")

    # Stability / fingerprint flags that are common on real installs and headless setups.
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")

    # Silence harmless console noise (SSL handshake / GCM "DEPRECATED_ENDPOINT"
    # errors) from Chrome's background services -- they don't affect scraping.
    # (enable-logging is also excluded via excludeSwitches above.)
    options.add_argument("--log-level=3")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-sync")

    driver = webdriver.Chrome(options=options)

    # Scrub navigator.webdriver, which automation normally leaves set to true.
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": "Object.defineProperty(navigator, 'webdriver', "
                          "{get: () => undefined});"
            },
        )
    except WebDriverException:
        pass  # Non-Chromium driver; ignore.

    return driver


# The anti-bot / consent button on tomestone.gg ("I am a human and not a bot").
ANTI_BOT_BUTTON_SELECTOR = "#cookie-consent-accept"

# The character "activity" page exposes the progress pull count for a specific
# encounter. We build it from the base character link in the JSON by appending
# this query, e.g.
#   https://tomestone.gg/character/35616835/bren-ito
#     + ACTIVITY_QUERY ->
#   https://tomestone.gg/character/35616835/bren-ito/activity?category=...
ACTIVITY_QUERY = (
    "/activity?category=ultimates&encounter=dancing-mad-ultimate"
    "&expansion=dawntrail&zone=ultimates"
)


def build_activity_link(link):
    """Build the encounter activity URL from a base character link."""
    return link.rstrip("/") + ACTIVITY_QUERY


def scrape_pull_count(driver, soup):
    """Read the 'Progress pull count' value from a character activity page.

    The markup looks like:
        <div>Progress pull count: <span class="mx-1 font-bold text-wipe">453</span></div>
    We anchor on the label text so we don't accidentally grab the
    identically-styled "Time spent progressing" span next to it.
    """
    label = soup.find(string=re.compile(r"Progress pull count"))
    if not label:
        return "N/A"
    parent = label.find_parent("div")
    span = parent.find("span") if parent else None
    if span and span.get_text(strip=True):
        return span.get_text(strip=True)
    return "N/A"


def pass_anti_bot(driver, timeout=10):
    """Detect and click the anti-bot button on the page before scraping.

    tomestone.gg shows a "I am a human and not a bot" button (id
    'cookie-consent-accept') directly on the page -- no iframe. We click it by
    id. If it isn't present this is a quick no-op.
    """
    try:
        WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ANTI_BOT_BUTTON_SELECTOR))
        )
    except TimeoutException:
        return False  # No anti-bot button on this page.

    # The page re-renders around this button, so the element reference can go
    # stale between locating and clicking. Re-locate and click in a retry loop.
    for attempt in range(5):
        try:
            button = driver.find_element(By.CSS_SELECTOR, ANTI_BOT_BUTTON_SELECTOR)
            label = button.text.strip() or "[no text]"
            # JS click avoids issues with overlays / off-screen elements.
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
            try:
                button.click()
            except WebDriverException:
                driver.execute_script("arguments[0].click();", button)
            print(f"Clicked anti-bot button: {label}")
            # Let the page reload / settle after the gate clears.
            time.sleep(4)
            return True
        except StaleElementReferenceException:
            time.sleep(0.5)  # DOM re-rendered; re-locate and retry.
            continue
        except NoSuchElementException:
            return False  # Button vanished (gate already cleared).
        except WebDriverException as e:
            print(f"Could not click anti-bot button: {e}")
            return False

    print("Could not click anti-bot button: element kept going stale.")
    return False


def scrape_data(entries):
    driver = build_driver()
    # Once we accept the consent/anti-bot gate it sets a cookie for the whole
    # session, so we only need to wait the full timeout until the first accept;
    # after that a short probe is enough in case it ever re-renders.
    gate_passed = False

    for entry in entries:
        if entry.get("cleared", False):
            entry["status"] = "cleared"
            entry["percent"] = "N/A"
            entry["pulls"] = "N/A"
            continue

        link = entry.get("link")
        if not link:
            print(f"Skipping {entry['name']}: No link provided.")
            entry["status"] = "No link"
            entry["percent"] = "N/A"
            entry["pulls"] = "N/A"
            continue

        entry.setdefault("pulls", "N/A")

        try:
            # The encounter activity page carries both the progress percentage
            # and the pull count, so a single visit covers everything.
            driver.get(build_activity_link(link))
            time.sleep(2)  # Wait for the page to load

            # Clear the "verify you are human" gate before reading the page.
            if pass_anti_bot(driver, timeout=2 if gate_passed else 10):
                gate_passed = True

            # The pull count is rendered asynchronously and doesn't appear
            # immediately, so give the page a moment to finish loading it.
            time.sleep(5)

            soup = BeautifulSoup(driver.page_source, "html.parser")
            progressing_div = soup.find("div", string="Progressing:")

            if progressing_div:
                percentage_div = progressing_div.find_next("div", class_="rounded-full")
                if percentage_div:
                    percentage_text = percentage_div.find("span", string=True)
                    if percentage_text:
                        status = percentage_text.string.strip()
                        entry["status"] = status
                        entry["percent"] = status.split(" ")[1]

            if "status" not in entry:
                entry["status"] = "Not found"
                entry["percent"] = "N/A"

            entry["pulls"] = scrape_pull_count(driver, soup)
        except Exception as e:
            print(f"Error processing {entry['name']}: {e}")

    driver.quit()

# Sorting functionality

def sort_entries(entries):
    """Sort entries with cleared first, then by phase and percentage."""
    # Define the target date for comparison
    target_date = datetime.strptime("11/26/2024", "%m/%d/%Y")

    def sorting_key(entry):
        # Check if the entry is cleared
        is_cleared = entry.get("status", "").lower() == "cleared"
        date = entry.get("date", "")
        status = entry.get("status", "")

        # Parse date for cleared entries
        try:
            entry_date = datetime.strptime(date, "%m/%d/%Y") if is_cleared else None
        except ValueError:
            entry_date = None

        # Cleared entries are sorted by proximity to the target date
        if is_cleared:
            date_diff = abs((entry_date - target_date).days) if entry_date else float("inf")
            return (0, date_diff)

        # Non-cleared entries are sorted by descending phase and ascending
        # percent. The percent is the boss's remaining HP, so a lower percent
        # means more progress and should rank higher. Capture the full decimal
        # value (e.g. "73.47") rather than just the digits before the '%'.
        match = re.search(r"([\d.]+)%.*?P(\d+)", status)
        if match:
            percent = float(match.group(1))
            phase = int(match.group(2))
            return (1, -phase, percent)  # Sort by descending phase, ascending percent

        # Default for unmatched entries
        return (2, float("inf"), float("inf"))

    # Sort using the custom key
    return sorted(entries, key=sorting_key)

# Main functionality

def main():
    json_file_path = "./ladder.json"
    output_csv_path = "./outputs/output.csv"
    sorted_csv_path = "./outputs/sorted_output.csv"
    leaderboard_path = "./outputs/leaderboard.txt"

    # Step 1: Load JSON
    data = load_json(json_file_path)

    # Step 2: Scrape data and update entries
    scrape_data(data)

    # Step 3: Write output.csv
    save_csv(data, output_csv_path, ["name", "link", "percent", "pulls", "status", "cleared", "date", "discord"])

    # Step 4: Sort entries
    sorted_data = sort_entries(data)

    # Step 5: Write sorted_output.csv
    save_csv(sorted_data, sorted_csv_path, ["name", "link", "percent", "pulls", "status", "cleared", "date", "discord"])

    # Step 6: Generate leaderboard.txt
    cleared = [entry for entry in sorted_data if entry["status"] == "cleared"]
    non_cleared = [entry for entry in sorted_data if entry["status"] != "cleared"]

    write_leaderboard(cleared, non_cleared, leaderboard_path)

    print("All tasks completed successfully!")

if __name__ == "__main__":
    main()
