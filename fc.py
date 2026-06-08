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
from PIL import Image, ImageDraw, ImageFont
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


# ---- Leaderboard image rendering -------------------------------------------

# Gruvbox dark palette (https://github.com/morhetz/gruvbox).
GB_BG = (40, 40, 40)        # #282828 bg0  - page background
GB_FG = (235, 219, 178)     # #ebdbb2 fg   - primary text
GB_GRAY = (146, 131, 116)   # #928374 gray - box borders / rank
GB_YELLOW = (250, 189, 47)  # #fabd2f      - P1 / title
GB_BLUE = (131, 165, 152)   # #83a598      - P2
GB_GREEN = (184, 187, 38)   # #b8bb26      - P3
GB_RED = (251, 73, 52)      # #fb4934      - P4
GB_ORANGE = (254, 128, 25)  # #fe8019      - cleared
GB_PURPLE = (211, 134, 155)  # #d3869b     - P5
GB_AQUA = (142, 192, 124)   # #8ec07c      - header labels
GB_ROW_ALT = (60, 56, 54)   # #3c3836 bg1  - alternating row shade
GB_HEADER_BG = (50, 48, 47) # #32302f bg0s - header strip

# Progress text colour by phase (higher phase == further along).
PHASE_COLORS = {
    1: GB_YELLOW,
    2: GB_BLUE,
    3: GB_GREEN,
    4: GB_RED,
    5: GB_PURPLE,
}
CLEARED_COLOR = GB_ORANGE


def _load_mono_font(size):
    """Load a monospace TrueType font (with box-drawing glyphs)."""
    candidates = [
        "MapleMono-NF-Regular.ttf", "C:/Windows/Fonts/MapleMono-NF-Regular.ttf",
        "MapleMono-Regular.ttf", "MapleMonoNF-Regular.ttf",
        "consola.ttf", "C:/Windows/Fonts/consola.ttf",
        "DejaVuSansMono.ttf", "cour.ttf", "C:/Windows/Fonts/cour.ttf",
    ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _progress_display(entry):
    """Return (text, color) describing an entry's progress for the table."""
    status = entry.get("status", "")
    if status.lower() == "cleared":
        return "CLEARED", CLEARED_COLOR
    match = re.search(r"([\d.]+)%.*?P(\d+)", status)
    if match:
        percent, phase = match.group(1), int(match.group(2))
        return f"P{phase} {percent}%", PHASE_COLORS.get(phase, GB_FG)
    return status or "N/A", GB_GRAY


def write_leaderboard_image(entries, file_path):
    """Render the leaderboard as an ASCII box-drawing table (gruvbox).

    Cleared players and progressing players are split into their own sections
    -- mirroring leaderboard.txt -- each with its own column header and a rank
    that restarts at 1.
    """
    try:
        font = _load_mono_font(26)

        # Monospace metrics: every glyph (including box-drawing) occupies a
        # cell of char_w x line_h, so we can place text on a character grid.
        scratch = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        char_w = scratch.textlength("M", font=font)
        ascent, descent = font.getmetrics()
        line_h = ascent + descent

        title = "DMU PROGRESS LEADERBOARD"

        def pulls_of(entry):
            p = entry.get("pulls", "N/A")
            return "N/A" if p in ("", None) else str(p)

        # Split into sections, each numbered from 1. A row is
        # (rank, name, col3_text, col3_color, pulls).
        cleared_entries = [e for e in entries if e.get("status", "").lower() == "cleared"]
        proggin_entries = [e for e in entries if e.get("status", "").lower() != "cleared"]

        cleared_rows = []
        for i, e in enumerate(cleared_entries, start=1):
            cleared_rows.append((str(i), e.get("name", ""),
                                 e.get("date") or "—", CLEARED_COLOR, pulls_of(e)))

        proggin_rows = []
        for i, e in enumerate(proggin_entries, start=1):
            text, color = _progress_display(e)
            proggin_rows.append((str(i), e.get("name", ""), text, color, pulls_of(e)))

        # (band label, label color, col-3 header, rows) -- skip empty sections.
        sections = []
        if cleared_rows:
            sections.append(("CLEARED", CLEARED_COLOR, "Cleared", cleared_rows))
        if proggin_rows:
            sections.append(("PROGGIN'", GB_AQUA, "Progress", proggin_rows))

        # Column content widths (in characters), across every section.
        ncols = 4
        cw = [len("#"), len("Name"), max(len("Progress"), len("Cleared")), len("Pulls")]
        for _label, _lc, _h, sec_rows in sections:
            for rank, name, c3, _c3color, pulls in sec_rows:
                cw[0] = max(cw[0], len(rank))
                cw[1] = max(cw[1], len(name))
                cw[2] = max(cw[2], len(c3))
                cw[3] = max(cw[3], len(pulls))

        # Inner width spanned by a full-width (title / section band) row.
        inner_w = sum(c + 2 for c in cw) + (ncols - 1)

        def border(left, mid, right):
            return left + mid.join("─" * (c + 2) for c in cw) + right

        # Character column where each cell's content starts.
        # Layout per columned row: "│" + (" " + content + " " + "│") * ncols.
        content_start = []
        ci = 1  # past the leading border
        for c in range(ncols):
            ci += 1  # left pad space
            content_start.append(ci)
            ci += cw[c] + 1 + 1  # content + right pad + border

        def span_row(text, color):
            """A full-width row with centered text (title / section band)."""
            x = 1 + (inner_w - len(text)) // 2
            return [(0, "│" + " " * inner_w + "│", GB_GRAY), (x, text, color)]

        def cell_row(cells, colors):
            """A bordered, columned row as colored segments."""
            segs = [(0, border("│", "│", "│").replace("─", " "), GB_GRAY)]
            for c in range(ncols):
                segs.append((content_start[c], cells[c], colors[c]))
            return segs

        # Assemble lines, recording an optional background fill per line.
        lines, backgrounds = [], []

        def add(segments, bg=None):
            lines.append(segments)
            backgrounds.append(bg)

        add([(0, "┌" + "─" * inner_w + "┐", GB_GRAY)])              # title top
        add(span_row(title, GB_YELLOW))                            # title

        col_header_colors = [GB_GRAY, GB_AQUA, GB_AQUA, GB_AQUA]
        for si, (label, label_color, col3_header, sec_rows) in enumerate(sections):
            # Separator above the section band. Above is a full-width row for
            # the first section (title) and a columned data row otherwise.
            add([(0, border("├", "─", "┤") if si == 0 else border("├", "┴", "┤"),
                  GB_GRAY)])
            add(span_row(label, label_color), GB_HEADER_BG)        # section band
            add([(0, border("├", "┬", "┤"), GB_GRAY)])             # band -> cols
            add(cell_row(["#", "Name", col3_header, "Pulls"],
                         col_header_colors), GB_HEADER_BG)          # column header
            add([(0, border("├", "┼", "┤"), GB_GRAY)])             # header sep
            for i, (rank, name, c3, c3color, pulls) in enumerate(sec_rows):
                add(cell_row([rank, name, c3, pulls],
                             [GB_GRAY, GB_FG, c3color, GB_FG]),
                    GB_ROW_ALT if i % 2 == 1 else None)             # data row

        # Bottom border: columned if a section was rendered, else full-width.
        if sections:
            add([(0, border("└", "┴", "┘"), GB_GRAY)])
        else:
            add([(0, "└" + "─" * inner_w + "┘", GB_GRAY)])

        # Image size from the character grid, with a small margin.
        total_cols = inner_w + 2
        margin_x = int(char_w * 2)
        margin_y = line_h
        img_w = int(total_cols * char_w) + margin_x * 2
        img_h = line_h * len(lines) + margin_y * 2

        img = Image.new("RGB", (img_w, img_h), GB_BG)
        draw = ImageDraw.Draw(img)

        # Shade row interiors (between the left/right borders) for the section
        # bands, column headers, and alternating data rows.
        inner_left = margin_x + int(1 * char_w)
        inner_right = margin_x + int((total_cols - 1) * char_w)
        for row_idx, bg in enumerate(backgrounds):
            if bg is None:
                continue
            y = margin_y + row_idx * line_h
            draw.rectangle([inner_left, y, inner_right, y + line_h], fill=bg)

        for row_idx, segments in enumerate(lines):
            y = margin_y + row_idx * line_h
            for char_idx, text, color in segments:
                x = margin_x + int(char_idx * char_w)
                draw.text((x, y), text, font=font, fill=color, anchor="la")

        img.save(file_path)
        print(f"Leaderboard image successfully written to {file_path}")
    except Exception as e:
        print(f"Error writing leaderboard image: {e}")

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
    leaderboard_image_path = "./outputs/leaderboard.png"

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

    # Step 7: Generate leaderboard.png (styled ranked table)
    write_leaderboard_image(sorted_data, leaderboard_image_path)

    print("All tasks completed successfully!")

if __name__ == "__main__":
    main()
