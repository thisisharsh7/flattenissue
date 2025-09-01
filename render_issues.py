#!/usr/bin/env python3
"""
Flatten GitHub issues from a repository into a single static HTML page for fast skimming and Ctrl+F.
Inspired by rendergit by Andrej Karpathy.
"""

from __future__ import annotations
import argparse
import html
import json
import pathlib
import sys
import tempfile
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
import re

try:
    import markdown
except ImportError:
    print("Error: 'markdown' package is required. Install it with: pip install markdown", file=sys.stderr)
    sys.exit(1)

@dataclass
class Comment:
    body: str
    author: str
    created_at: str
    html_url: str

@dataclass
class Issue:
    number: int
    title: str
    body: str
    state: str  # "open" or "closed"
    labels: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    author: str = ""
    html_url: str = ""
    comments: List[Comment] = field(default_factory=list)
    milestone: Optional[str] = None

def make_github_request(url: str, token: Optional[str] = None) -> Dict[str, Any]:
    """Make a request to the GitHub API with optional authentication."""
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "GitHub-Issues-Renderer/1.0"
    }
    if token:
        headers["Authorization"] = f"token {token}"
    
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                return json.loads(response.read().decode('utf-8'))
            else:
                print(f"HTTP {response.status}: {response.reason}", file=sys.stderr)
                sys.exit(1)
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print("Error: GitHub API rate limit exceeded. Use a personal access token with --token", file=sys.stderr)
        else:
            print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error making request: {e}", file=sys.stderr)
        sys.exit(1)

def parse_repo_url(url: str) -> tuple[str, str]:
    """Extract owner and repo from GitHub URL."""
    # Handle various GitHub URL formats
    url = url.rstrip('/')
    if url.endswith('.git'):
        url = url[:-4]
    
    # Extract from https://github.com/owner/repo
    if 'github.com/' in url:
        parts = url.split('github.com/')[-1].split('/')
        if len(parts) >= 2:
            return parts[0], parts[1]
    
    # Handle owner/repo format directly
    if '/' in url and not url.startswith('http'):
        parts = url.split('/')
        if len(parts) == 2:
            return parts[0], parts[1]
    
    raise ValueError(f"Could not parse repository from URL: {url}")

def fetch_issues(owner: str, repo: str, token: Optional[str] = None, include_comments: bool = False) -> List[Issue]:
    """Fetch all issues (open and closed) from a GitHub repository, excluding pull requests."""
    print(f"📥 Fetching issues from {owner}/{repo}...", file=sys.stderr)
    
    issues = []
    page = 1
    per_page = 100
    
    while True:
        # Fetch issues (excludes PRs by default in GitHub API)
        url = f"https://api.github.com/repos/{owner}/{repo}/issues?state=all&page={page}&per_page={per_page}"
        data = make_github_request(url, token)
        
        if not data:
            break
            
        page_issues = []
        for item in data:
            # Skip pull requests (they have a 'pull_request' field)
            if 'pull_request' in item:
                continue
                
            issue = Issue(
                number=item['number'],
                title=item['title'],
                body=item.get('body', '') or '',
                state=item['state'],
                labels=item.get('labels', []),
                created_at=item['created_at'],
                updated_at=item['updated_at'],
                author=item['user']['login'],
                html_url=item['html_url'],
                milestone=item['milestone']['title'] if item.get('milestone') else None
            )
            
            # Fetch comments if requested
            if include_comments and item['comments'] > 0:
                comments_url = item['comments_url']
                comments_data = make_github_request(comments_url, token)
                for comment_data in comments_data:
                    comment = Comment(
                        body=comment_data.get('body', '') or '',
                        author=comment_data['user']['login'],
                        created_at=comment_data['created_at'],
                        html_url=comment_data['html_url']
                    )
                    issue.comments.append(comment)
            
            page_issues.append(issue)
        
        issues.extend(page_issues)
        print(f"  📄 Fetched page {page} ({len(page_issues)} issues)", file=sys.stderr)
        
        if len(data) < per_page:
            break
        page += 1
    
    print(f"✓ Fetched {len(issues)} total issues", file=sys.stderr)
    return issues

def slugify(text: str) -> str:
    """Simple slug generation for anchors."""
    # Keep alphanumeric, spaces, hyphens, underscores
    cleaned = re.sub(r'[^\w\s-]', '', text)
    # Replace spaces and multiple hyphens with single hyphen
    slug = re.sub(r'[-\s]+', '-', cleaned)
    return slug.strip('-').lower()

def format_date(iso_date: str) -> str:
    """Format ISO date to human readable format."""
    try:
        dt = datetime.fromisoformat(iso_date.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M')
    except:
        return iso_date

def render_markdown_text(md_text: str) -> str:
    """Render markdown to HTML."""
    if not md_text.strip():
        return '<p><em>No description provided.</em></p>'
    return markdown.markdown(md_text, extensions=['fenced_code', 'tables', 'toc'])

def generate_labels_html(labels: List[Dict[str, Any]]) -> str:
    """Generate HTML for issue labels."""
    if not labels:
        return ""
    
    label_spans = []
    for label in labels:
        name = html.escape(label['name'])
        color = label.get('color', '666666')
        # Calculate contrast color for text
        text_color = '#000' if int(color, 16) > 0x808080 else '#fff'
        label_spans.append(
            f'<span class="label" style="background-color: #{color}; color: {text_color};">{name}</span>'
        )
    
    return f'<div class="labels">{"".join(label_spans)}</div>'

def generate_cxml_text(issues: List[Issue], owner: str, repo: str) -> str:
    """Generate CXML format text for LLM consumption."""
    lines = ["<documents>"]
    lines.append(f"<repository>{owner}/{repo}</repository>")

    for index, issue in enumerate(issues, 1):
        lines.append(f'<document index="{index}">')
        lines.append(f"<source>Issue #{issue.number}: {issue.title}</source>")
        lines.append(f"<metadata>")
        lines.append(f"  <state>{issue.state}</state>")
        lines.append(f"  <author>{issue.author}</author>")
        lines.append(f"  <created>{issue.created_at}</created>")
        if issue.labels:
            label_names = [label['name'] for label in issue.labels]
            lines.append(f"  <labels>{', '.join(label_names)}</labels>")
        if issue.milestone:
            lines.append(f"  <milestone>{issue.milestone}</milestone>")
        lines.append(f"</metadata>")
        lines.append("<document_content>")
        lines.append(f"# {issue.title}")
        lines.append("")
        lines.append(issue.body)
        
        if issue.comments:
            lines.append("")
            lines.append("## Comments")
            for comment in issue.comments:
                lines.append(f"### Comment by {comment.author} ({format_date(comment.created_at)})")
                lines.append(comment.body)
                lines.append("")
        
        lines.append("</document_content>")
        lines.append("</document>")

    lines.append("</documents>")
    return "\n".join(lines)

def build_sidebar_navigation(issues: List[Issue]) -> Dict[str, str]:
    """Build sidebar navigation by labels and milestones."""
    # Group issues by labels
    label_groups = {}
    milestone_groups = {}
    
    for issue in issues:
        # Group by labels
        if issue.labels:
            for label in issue.labels:
                label_name = label['name']
                if label_name not in label_groups:
                    label_groups[label_name] = []
                label_groups[label_name].append(issue)
        else:
            if 'unlabeled' not in label_groups:
                label_groups['unlabeled'] = []
            label_groups['unlabeled'].append(issue)
        
        # Group by milestones
        milestone = issue.milestone or 'No Milestone'
        if milestone not in milestone_groups:
            milestone_groups[milestone] = []
        milestone_groups[milestone].append(issue)
    
    # Generate HTML for sidebar
    sidebar_html = []
    
    # All issues
    sidebar_html.append(f'<div class="nav-section">')
    sidebar_html.append(f'<h3>All Issues ({len(issues)})</h3>')
    sidebar_html.append(f'<ul class="nav-list">')
    for issue in sorted(issues, key=lambda x: x.number):
        anchor = f"issue-{issue.number}"
        state_class = issue.state
        sidebar_html.append(f'<li><a href="#{anchor}" class="{state_class}">#{issue.number}: {html.escape(issue.title[:50])}{"..." if len(issue.title) > 50 else ""}</a></li>')
    sidebar_html.append(f'</ul>')
    sidebar_html.append(f'</div>')
    
    # By labels
    if len(label_groups) > 1:  # More than just unlabeled
        sidebar_html.append(f'<div class="nav-section">')
        sidebar_html.append(f'<h3>By Labels</h3>')
        for label_name, label_issues in sorted(label_groups.items()):
            if label_name == 'unlabeled':
                continue
            sidebar_html.append(f'<details>')
            sidebar_html.append(f'<summary>{html.escape(label_name)} ({len(label_issues)})</summary>')
            sidebar_html.append(f'<ul class="nav-list">')
            for issue in sorted(label_issues, key=lambda x: x.number):
                anchor = f"issue-{issue.number}"
                state_class = issue.state
                sidebar_html.append(f'<li><a href="#{anchor}" class="{state_class}">#{issue.number}: {html.escape(issue.title[:40])}{"..." if len(issue.title) > 40 else ""}</a></li>')
            sidebar_html.append(f'</ul>')
            sidebar_html.append(f'</details>')
        sidebar_html.append(f'</div>')
    
    # By milestones
    if len(milestone_groups) > 1:  # More than just "No Milestone"
        sidebar_html.append(f'<div class="nav-section">')
        sidebar_html.append(f'<h3>By Milestones</h3>')
        for milestone, milestone_issues in sorted(milestone_groups.items()):
            sidebar_html.append(f'<details>')
            sidebar_html.append(f'<summary>{html.escape(milestone)} ({len(milestone_issues)})</summary>')
            sidebar_html.append(f'<ul class="nav-list">')
            for issue in sorted(milestone_issues, key=lambda x: x.number):
                anchor = f"issue-{issue.number}"
                state_class = issue.state
                sidebar_html.append(f'<li><a href="#{anchor}" class="{state_class}">#{issue.number}: {html.escape(issue.title[:40])}{"..." if len(issue.title) > 40 else ""}</a></li>')
            sidebar_html.append(f'</ul>')
            sidebar_html.append(f'</details>')
        sidebar_html.append(f'</div>')
    
    return "".join(sidebar_html)

def build_html(owner: str, repo: str, issues: List[Issue], include_comments: bool = False) -> str:
    """Build the complete HTML page."""
    
    # Statistics
    open_issues = [i for i in issues if i.state == "open"]
    closed_issues = [i for i in issues if i.state == "closed"]
    
    # Sidebar navigation
    sidebar_nav = build_sidebar_navigation(issues)
    
    # Generate CXML text for LLM view
    cxml_text = generate_cxml_text(issues, owner, repo)
    
    # Render issue cards
    issue_cards = []
    for issue in sorted(issues, key=lambda x: x.number):
        anchor = f"issue-{issue.number}"
        
        # Labels
        labels_html = generate_labels_html(issue.labels)
        
        # Body content
        body_html = render_markdown_text(issue.body)
        
        # Comments
        comments_html = ""
        if include_comments and issue.comments:
            comments_html = '<div class="comments"><h4>Comments:</h4>'
            for comment in issue.comments:
                comment_body = render_markdown_text(comment.body)
                comments_html += f'''
                <div class="comment">
                    <div class="comment-meta">
                        <strong>{html.escape(comment.author)}</strong> • 
                        <time>{format_date(comment.created_at)}</time>
                    </div>
                    <div class="comment-body">{comment_body}</div>
                </div>
                '''
            comments_html += '</div>'
        
        # Milestone
        milestone_html = ""
        if issue.milestone:
            milestone_html = f'<div class="milestone">📋 <strong>Milestone:</strong> {html.escape(issue.milestone)}</div>'
        
        state_class = "open" if issue.state == "open" else "closed"
        state_icon = "🟢" if issue.state == "open" else "🔴"
        
        issue_cards.append(f'''
<section class="issue-card {state_class}" id="{anchor}">
    <div class="issue-header">
        <h2>
            <a href="{html.escape(issue.html_url)}" target="_blank" class="issue-link">
                #{issue.number}: {html.escape(issue.title)}
            </a>
            <span class="state-badge {state_class}">{state_icon} {issue.state.title()}</span>
        </h2>
        <div class="issue-meta">
            <span><strong>Author:</strong> {html.escape(issue.author)}</span> • 
            <span><strong>Created:</strong> <time>{format_date(issue.created_at)}</time></span> • 
            <span><strong>Updated:</strong> <time>{format_date(issue.updated_at)}</time></span>
        </div>
        {labels_html}
        {milestone_html}
    </div>
    <div class="issue-body">
        {body_html}
    </div>
    {comments_html}
    <div class="back-top"><a href="#top">↑ Back to top</a></div>
</section>
        ''')
    
    repo_url = f"https://github.com/{owner}/{repo}"
    
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>GitHub Issues - {html.escape(owner)}/{html.escape(repo)}</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    margin: 0; padding: 0; line-height: 1.6;
    background-color: #fafbfc;
  }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 0 1rem; }}
  
  /* Layout with sidebar */
  .page {{ display: grid; grid-template-columns: 300px minmax(0,1fr); gap: 0; min-height: 100vh; }}
  
  #sidebar {{
    position: sticky; top: 0; align-self: start;
    height: 100vh; overflow-y: auto;
    border-right: 1px solid #e1e4e8; background: #f6f8fa;
    padding: 1rem;
  }}
  #sidebar h3 {{ margin: 1.5rem 0 0.5rem 0; font-size: 0.9rem; color: #586069; text-transform: uppercase; }}
  #sidebar h3:first-child {{ margin-top: 0; }}
  
  .nav-section {{ margin-bottom: 1.5rem; }}
  .nav-list {{ list-style: none; padding: 0; margin: 0; }}
  .nav-list li {{ margin: 0.25rem 0; }}
  .nav-list a {{ 
    text-decoration: none; color: #0366d6; display: block;
    padding: 0.25rem 0.5rem; border-radius: 6px; font-size: 0.85rem;
  }}
  .nav-list a:hover {{ background-color: #e1e4e8; }}
  .nav-list a.open {{ border-left: 3px solid #28a745; }}
  .nav-list a.closed {{ border-left: 3px solid #d73a49; }}
  
  details {{ margin: 0.5rem 0; }}
  details summary {{ cursor: pointer; font-weight: 500; padding: 0.25rem; }}
  details summary:hover {{ background-color: #e1e4e8; border-radius: 6px; }}
  
  main.container {{ padding: 1rem; background: white; }}
  
  .header {{ 
    background: white; border-bottom: 1px solid #e1e4e8; 
    padding: 1rem 0; margin-bottom: 1.5rem;
  }}
  .repo-info {{ color: #586069; }}
  .stats {{ margin-top: 0.5rem; display: flex; gap: 1rem; }}
  .stat {{ padding: 0.5rem 1rem; background: #f6f8fa; border-radius: 6px; font-size: 0.9rem; }}
  .stat.open {{ border-left: 4px solid #28a745; }}
  .stat.closed {{ border-left: 4px solid #d73a49; }}
  
  /* View toggle */
  .view-toggle {{
    margin: 1rem 0;
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }}
  .toggle-btn {{
    padding: 0.5rem 1rem;
    border: 1px solid #d1d5da;
    background: white;
    cursor: pointer;
    border-radius: 6px;
    font-size: 0.9rem;
  }}
  .toggle-btn.active {{
    background: #0366d6;
    color: white;
    border-color: #0366d6;
  }}
  .toggle-btn:hover:not(.active) {{ background: #f6f8fa; }}
  
  /* Issue cards */
  .issue-card {{
    background: white; border: 1px solid #e1e4e8;
    border-radius: 6px; margin-bottom: 1rem; padding: 1.5rem;
    box-shadow: 0 1px 0 rgba(27,31,35,0.04);
  }}
  .issue-card.open {{ border-left: 4px solid #28a745; }}
  .issue-card.closed {{ border-left: 4px solid #d73a49; }}
  
  .issue-header h2 {{ 
    margin: 0 0 0.75rem 0; display: flex; align-items: center; gap: 0.5rem;
  }}
  .issue-link {{ text-decoration: none; color: #24292e; flex: 1; }}
  .issue-link:hover {{ color: #0366d6; }}
  
  .state-badge {{
    font-size: 0.8rem; padding: 0.25rem 0.5rem; 
    border-radius: 12px; white-space: nowrap;
  }}
  .state-badge.open {{ background: #dcffe4; color: #28a745; }}
  .state-badge.closed {{ background: #ffeef0; color: #d73a49; }}
  
  .issue-meta {{ color: #586069; font-size: 0.9rem; margin-bottom: 0.75rem; }}
  .labels {{ margin: 0.75rem 0; }}
  .label {{ 
    display: inline-block; padding: 0.25rem 0.5rem; 
    border-radius: 12px; font-size: 0.75rem; font-weight: 500;
    margin-right: 0.5rem; margin-bottom: 0.25rem;
  }}
  .milestone {{ color: #586069; font-size: 0.9rem; margin: 0.5rem 0; }}
  
  .issue-body {{ margin: 1rem 0; }}
  .issue-body p:first-child {{ margin-top: 0; }}
  .issue-body p:last-child {{ margin-bottom: 0; }}
  
  .comments {{ margin-top: 1.5rem; }}
  .comments h4 {{ color: #586069; border-bottom: 1px solid #e1e4e8; padding-bottom: 0.5rem; }}
  .comment {{ 
    background: #f6f8fa; border: 1px solid #e1e4e8;
    border-radius: 6px; padding: 1rem; margin: 0.75rem 0;
  }}
  .comment-meta {{ color: #586069; font-size: 0.9rem; margin-bottom: 0.5rem; }}
  
  .back-top {{ margin-top: 1rem; font-size: 0.9rem; }}
  .back-top a {{ color: #586069; text-decoration: none; }}
  .back-top a:hover {{ color: #0366d6; }}
  
  /* LLM view */
  #llm-view {{ display: none; }}
  #llm-text {{
    width: 100%;
    height: 70vh;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 0.85em;
    border: 1px solid #d1d5da;
    border-radius: 6px;
    padding: 1rem;
    resize: vertical;
    background: #f6f8fa;
  }}
  .copy-hint {{
    margin-top: 0.5rem;
    color: #586069;
    font-size: 0.9em;
  }}
  
  /* Code styling */
  pre {{ background: #f6f8fa; padding: 1rem; border-radius: 6px; overflow-x: auto; }}
  code {{ 
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    background: #f6f8fa; padding: 0.2rem 0.4rem; border-radius: 3px; font-size: 0.9em;
  }}
  pre code {{ background: none; padding: 0; }}
  
  blockquote {{ 
    border-left: 4px solid #ddd; margin: 1rem 0; 
    padding-left: 1rem; color: #586069; 
  }}
  
  :target {{ scroll-margin-top: 20px; }}
  
  @media (max-width: 768px) {{
    .page {{ grid-template-columns: 1fr; }}
    #sidebar {{ position: relative; height: auto; }}
  }}
</style>
</head>
<body>
<a id="top"></a>

<div class="page">
  <nav id="sidebar">
    <div><a href="#top">↑ Back to top</a></div>
    {sidebar_nav}
  </nav>

  <main class="container">
    <div class="header">
      <h1>📋 GitHub Issues</h1>
      <div class="repo-info">
        <strong>Repository:</strong> 
        <a href="{repo_url}" target="_blank">{html.escape(owner)}/{html.escape(repo)}</a>
      </div>
      <div class="stats">
        <div class="stat open">🟢 {len(open_issues)} Open</div>
        <div class="stat closed">🔴 {len(closed_issues)} Closed</div>
        <div class="stat">📊 {len(issues)} Total</div>
      </div>
    </div>

    <div class="view-toggle">
      <strong>View:</strong>
      <button class="toggle-btn active" onclick="showHumanView()">👤 Human</button>
      <button class="toggle-btn" onclick="showLLMView()">🤖 LLM</button>
    </div>

    <div id="human-view">
      {"".join(issue_cards)}
    </div>

    <div id="llm-view">
      <section>
        <h2>🤖 LLM View - CXML Format</h2>
        <p>Copy the text below and paste it to an LLM for analysis:</p>
        <textarea id="llm-text" readonly>{html.escape(cxml_text)}</textarea>
        <div class="copy-hint">
          💡 <strong>Tip:</strong> Click in the text area and press Ctrl+A (Cmd+A on Mac) to select all, then Ctrl+C (Cmd+C) to copy.
        </div>
      </section>
    </div>
  </main>
</div>

<script>
function showHumanView() {{
  document.getElementById('human-view').style.display = 'block';
  document.getElementById('llm-view').style.display = 'none';
  document.querySelectorAll('.toggle-btn').forEach(btn => btn.classList.remove('active'));
  event.target.classList.add('active');
}}

function showLLMView() {{
  document.getElementById('human-view').style.display = 'none';
  document.getElementById('llm-view').style.display = 'block';
  document.querySelectorAll('.toggle-btn').forEach(btn => btn.classList.remove('active'));
  event.target.classList.add('active');

  // Auto-select all text when switching to LLM view for easy copying
  setTimeout(() => {{
    const textArea = document.getElementById('llm-text');
    textArea.focus();
    textArea.select();
  }}, 100);
}}
</script>
</body>
</html>'''

def derive_output_path(owner: str, repo: str) -> pathlib.Path:
    """Derive output path from owner and repo."""
    filename = f"{owner}-{repo}-issues.html"
    return pathlib.Path(tempfile.gettempdir()) / filename

def main() -> int:
    parser = argparse.ArgumentParser(description="Render GitHub issues to a single HTML page")
    parser.add_argument("repo_url", help="GitHub repository URL or owner/repo")
    parser.add_argument("-o", "--out", help="Output HTML file path")
    parser.add_argument("-t", "--token", help="GitHub personal access token (recommended for higher API limits)")
    parser.add_argument("-c", "--comments", action="store_true", help="Include issue comments (slower)")
    parser.add_argument("--no-open", action="store_true", help="Don't open the HTML file in browser")
    
    args = parser.parse_args()
    
    try:
        owner, repo = parse_repo_url(args.repo_url)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    
    if not args.out:
        args.out = str(derive_output_path(owner, repo))
    
    try:
        issues = fetch_issues(owner, repo, args.token, args.comments)
        
        if not issues:
            print(f"No issues found in {owner}/{repo}", file=sys.stderr)
            return 0
        
        print(f"🔨 Generating HTML...", file=sys.stderr)
        html_content = build_html(owner, repo, issues, args.comments)
        
        output_path = pathlib.Path(args.out)
        print(f"💾 Writing HTML to {output_path.resolve()}", file=sys.stderr)
        output_path.write_text(html_content, encoding='utf-8')
        
        file_size = output_path.stat().st_size
        print(f"✓ Generated {file_size // 1024}KB file: {output_path}", file=sys.stderr)
        
        if not args.no_open:
            print(f"🌐 Opening in browser...", file=sys.stderr)
            webbrowser.open(f"file://{output_path.resolve()}")
        
        return 0
        
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())