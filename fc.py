import json
import csv
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
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
            file.write("## FRU Progress leaderboard\n\n")
            
            # Cleared section
            file.write("# Cleared!\n")
            for idx, entry in enumerate(cleared, start=1):
                file.write(f"{idx}. {entry['name']} - {entry['discord']}\n")
            
            file.write("\n# Proggin'\n")
            for idx, entry in enumerate(non_cleared, start=1):
                file.write(f"{idx}. {entry['name']} - {entry['status']}\n")

        print(f"Leaderboard successfully written to {file_path}")
    except Exception as e:
        print(f"Error writing leaderboard: {e}")

# Selenium functionality

def scrape_data(entries):
    options = webdriver.ChromeOptions()
    driver = webdriver.Chrome(options=options)

    for entry in entries:
        if entry.get("cleared", False):
            entry["status"] = "cleared"
            entry["percent"] = "N/A"
            continue

        link = entry.get("link")
        if not link:
            print(f"Skipping {entry['name']}: No link provided.")
            entry["status"] = "No link"
            entry["percent"] = "N/A"
            continue

        try:
            driver.get(link)
            time.sleep(2)  # Wait for the page to load

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
                        continue

            entry["status"] = "Not found"
            entry["percent"] = "N/A"
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

        # Non-cleared entries are sorted by descending phase and ascending percent
        match = re.match(r".*?(\d+)%.*?P(\d+)", status)
        if match:
            percent = int(match.group(1))
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
    save_csv(data, output_csv_path, ["name", "link", "percent", "status", "cleared", "date", "discord"])

    # Step 4: Sort entries
    sorted_data = sort_entries(data)

    # Step 5: Write sorted_output.csv
    save_csv(sorted_data, sorted_csv_path, ["name", "link", "percent", "status", "cleared", "date", "discord"])

    # Step 6: Generate leaderboard.txt
    cleared = [entry for entry in sorted_data if entry["status"] == "cleared"]
    non_cleared = [entry for entry in sorted_data if entry["status"] != "cleared"]

    write_leaderboard(cleared, non_cleared, leaderboard_path)

    print("All tasks completed successfully!")

if __name__ == "__main__":
    main()
