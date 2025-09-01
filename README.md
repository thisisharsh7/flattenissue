# flattenissue

Convert all GitHub issues from a repository into a single searchable HTML page. Inspired by [rendergit](https://github.com/karpathy/rendergit) by Andrej Karpathy.

## Installation

```bash
pip install markdown
```

## Usage

```bash
# Basic usage
python render_issues.py owner/repo

# With GitHub token (recommended for higher rate limits)
python render_issues.py owner/repo --token YOUR_GITHUB_TOKEN

# Include comments
python render_issues.py owner/repo --comments

# Custom output file
python render_issues.py owner/repo --out issues.html
```

## Features

- Fetches all open and closed issues (excludes pull requests)
- Single HTML file with embedded CSS and JavaScript
- Sidebar navigation by labels and milestones
- Two view modes: Human-friendly and LLM-ready format
- Fully searchable with Ctrl+F
- Colored labels and issue states
- Optional comments support

## Requirements

- Python 3.7+
- GitHub repository URL
- Optional: GitHub personal access token for higher API limits

## Output

Creates a standalone HTML file containing:
- All repository issues as cards
- Sidebar navigation
- Search functionality
- Direct links to original GitHub issues
- LLM-friendly CXML export format

## Credits

Inspired by [rendergit](https://github.com/karpathy/rendergit) by Andrej Karpathy.

Made with love by [Harsh Kumar](https://github.com/thisisharsh7).