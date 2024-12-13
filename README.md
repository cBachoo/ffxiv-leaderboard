# FFXIV Progress Leaderboard

## Overview

This project automates the process of scraping data from **Tomestone** to generate a leaderboard for tracking player progress. It fetches data for participants, sorts it based on their progress, and outputs the results in three formats:

- **Raw CSV**: `output.csv`
- **Sorted CSV**: `sorted_output.csv`
- **Leaderboard**: `leaderboard.txt`

The script also handles cases where players have cleared the content, prioritizing them in the leaderboard and sorting them by a target date for accuracy.

---

## Features

1. **Web Scraping**: Automates data extraction from Tomestone links.
2. **Sorting Logic**:
   - Cleared players are ranked highest, sorted by proximity to a `target-date`.
   - Non-cleared players are sorted by phase (higher phase is better) and percentage (lower is better).
3. **Customizable Output**: Generates three files: `output.csv`, `sorted_output.csv`, and `leaderboard.txt`.
4. **Modular Design**: Combines scraping, sorting, and leaderboard generation into one script.

---

## Setup

### Requirements

1. Python 3.8+

### Installation

1. Clone the repository:

   ```bash
   git clone <repository-url>
   cd <repository-directory>
   ```

2. Install the required Python packages:

   ```bash
   pip install -r requirements.txt
   ```

### Configuration

1. **Modify `ladder.json`**:

   - Include the following fields for each participant:

     ```json
     [
       {
         "name": "Player Name",
         "link": "tomestone-link",
         "cleared": false,
         "date": "", // For cleared participants
         "discord": "" // Discord timestamp (also for cleared participants)
       }
     ]
     ```

   - Ensure valid Tomestone links are provided for each participant.

---

## Usage

Run the master script to execute all functionalities:

```bash
python fc.py
```

### Outputs

1. **output.csv**:
   - Contains raw scraped data.
2. **sorted_output.csv**:
   - Sorted data based on cleared status, phase, percentage, and target date.
3. **leaderboard.txt**:
   - A Discord-ready formatted leaderboard.

---

## Notes

1. **Cleared Participants**:
   - If a participant has `cleared` set to `true`, they will not be scraped.
   - Their `discord` handle will appear in the cleared section of the leaderboard.
2. **Non-Cleared Participants**:
   - Sorted by phase and percentage dynamically scraped from Tomestone.
3. **Updating for New Content**:
   - Change the `target-date` in the script to the release date of the new content.

---

## Potential Issues

- Ensure all dependencies (e.g., ChromeDriver) are correctly installed and paths configured.
- Verify the JSON structure for any syntax errors.

---

