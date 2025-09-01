# GitHub Issues Renderer

A Python script that fetches all issues from a GitHub repository and renders them into a single, searchable HTML page. Inspired by [rendergit](https://github.com/karpathy/rendergit) by Andrej Karpathy.

## ✨ Features

- **Complete Issue Collection**: Fetches all open and closed issues (excludes pull requests)
- **Rich Content**: Includes issue titles, labels, body text, state, dates, and optional comments
- **Visual Design**: Issues rendered as cards with colored labels and state indicators
- **Smart Navigation**: Sidebar navigation organized by labels, milestones, and issue numbers
- **Dual View Modes**:
  - **👤 Human View**: Visually appealing cards with syntax highlighting and formatting
  - **🤖 LLM View**: Flattened CXML format optimized for AI analysis
- **Fully Searchable**: Use Ctrl+F to search across all issues and content
- **Self-Contained**: Single HTML file with embedded CSS and JavaScript
- **GitHub Integration**: Direct links to original issues and proper markdown rendering

## 📋 Requirements

- Python 3.7+
- `markdown` package for markdown rendering

## 🚀 Installation & Setup

1. **Clone or download this script**:
   ```bash
   # If you have the parent rendergit repo:
   cd github-issues-render
   
   # Or download just the render_issues.py file
   ```

2. **Install required dependencies**:
   ```bash
   pip install markdown
   ```

3. **Optional: Get a GitHub Personal Access Token** (recommended):
   - Go to GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
   - Generate a new token with `public_repo` scope (for public repos) or `repo` scope (for private repos)
   - No special permissions needed beyond reading repository data

## 📖 Usage

### Basic Usage

```bash
# Fetch issues from a public repository
python render_issues.py https://github.com/owner/repo

# Alternative formats (all equivalent):
python render_issues.py owner/repo
python render_issues.py https://github.com/owner/repo.git
```

### With GitHub Token (Recommended)

```bash
# Use token for higher API limits (5000 vs 60 requests/hour)
python render_issues.py owner/repo --token YOUR_GITHUB_TOKEN
```
  python render_issues.py https://github.com/epicenter-so/epicenter
### Advanced Options

```bash
# Include comments in each issue (slower, uses more API calls)
python render_issues.py owner/repo --comments --token YOUR_TOKEN

# Specify custom output file
python render_issues.py owner/repo --out my-issues.html

# Don't automatically open in browser
python render_issues.py owner/repo --no-open
```

### Full Example

```bash
# Fetch all issues with comments from a popular repo
python render_issues.py microsoft/vscode --token ghp_xxxxx --comments --out vscode-issues.html
```

## 📊 What Gets Included

### ✅ Included
- ✅ All open and closed **issues**
- ✅ Issue titles, numbers, and body text
- ✅ Labels with original colors
- ✅ Issue state (open/closed) with visual indicators
- ✅ Creation and update timestamps
- ✅ Author information
- ✅ Milestone assignments
- ✅ Markdown formatting in issue bodies
- ✅ Comments (when `--comments` flag is used)
- ✅ Direct links to original GitHub issues

### ❌ Excluded
- ❌ Pull requests (GitHub API separates these from issues)
- ❌ Issue events (labels added/removed, assignments, etc.)
- ❌ Reactions and emoji responses
- ❌ File attachments and images (links preserved)

## 🔧 Command Line Options

```
positional arguments:
  repo_url              GitHub repository URL or owner/repo

options:
  -h, --help            Show help message
  -o, --out OUTPUT      Output HTML file path (default: temp file based on repo name)
  -t, --token TOKEN     GitHub personal access token (recommended for higher API limits)
  -c, --comments        Include issue comments (slower, requires more API calls)
  --no-open             Don't automatically open the HTML file in browser
```

## 📄 Output

The script generates a single HTML file with:

1. **Repository Information**: Name, link, and statistics
2. **Navigation Sidebar**:
   - All issues (chronological)
   - Issues grouped by labels
   - Issues grouped by milestones
3. **Issue Cards**: Each issue displayed as a card with all metadata
4. **View Toggle**: Switch between Human and LLM views
5. **Search**: Full-text search with Ctrl+F

## 🤖 LLM Integration

The LLM view provides issues in CXML format, perfect for AI analysis:

```xml
<documents>
<repository>owner/repo</repository>
<document index="1">
<source>Issue #123: Bug in authentication</source>
<metadata>
  <state>open</state>
  <author>username</author>
  <created>2023-01-01T12:00:00Z</created>
  <labels>bug, authentication</labels>
</metadata>
<document_content>
# Bug in authentication

The login system fails when...
</document_content>
</document>
</documents>
```

## ⚡ Performance & Rate Limits

### GitHub API Limits
- **Without token**: 60 requests/hour
- **With token**: 5,000 requests/hour

### API Usage
- **Basic issues**: ~1 request per 100 issues
- **With comments**: +1 request per issue that has comments

### Recommendations
- Always use a personal access token for repositories with many issues
- For repositories with 1000+ issues and many comments, expect longer fetch times
- The script shows progress as it fetches each page

## 🔍 Example Repositories to Try

```bash
# Small repo - quick test
python render_issues.py karpathy/rendergit

# Medium repo - good example
python render_issues.py microsoft/TypeScript --token YOUR_TOKEN

# Large repo - comprehensive test (will take time)
python render_issues.py microsoft/vscode --token YOUR_TOKEN
```

## 🐛 Troubleshooting

### Common Issues

1. **Rate limit exceeded**:
   ```
   Error: GitHub API rate limit exceeded. Use a personal access token with --token
   ```
   **Solution**: Get a GitHub token and use the `--token` parameter

2. **Repository not found**:
   ```
   HTTP Error 404: Not Found
   ```
   **Solution**: Verify the repository URL and ensure it's public (or use a token with private repo access)

3. **Module not found**:
   ```
   ImportError: No module named 'markdown'
   ```
   **Solution**: Install dependencies with `pip install markdown`

### Debug Tips

- Start with a small repository to test your setup
- Check that the repository actually has issues (not just pull requests)
- Verify your GitHub token has the right permissions
- Use `--no-open` if you have issues with the browser opening automatically

## 🔗 Related Projects

- [rendergit](https://github.com/karpathy/rendergit) - The inspiration for this project (flattens code repositories)
- [GitHub CLI](https://cli.github.com/) - Official GitHub command-line tool
- [gh-issues](https://github.com/github/gh-issues) - GitHub's official issues extension

## 📝 License

This project follows the same license as its inspiration (rendergit). Feel free to modify and distribute.