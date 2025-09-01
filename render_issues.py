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
    # Sort by creation date, newest first (same as main content)
    for issue in sorted(issues, key=lambda x: x.created_at, reverse=True):
        anchor = f"issue-{issue.number}"
        state_class = issue.state
        sidebar_html.append(f'<li><a href="#{anchor}" class="{state_class}">#{issue.number}: {html.escape(issue.title[:50])}{"..." if len(issue.title) > 50 else ""}</a></li>')
    sidebar_html.append(f'</ul>')
    sidebar_html.append(f'</div>')
    
    # Remove label groups from sidebar - they're now in the main header as filter chips
    
    # Keep milestones in sidebar but make it optional
    if len(milestone_groups) > 1 and any(m != 'No Milestone' for m in milestone_groups.keys()):
        sidebar_html.append(f'<div class="nav-section">')
        sidebar_html.append(f'<h3>Milestones</h3>')
        for milestone, milestone_issues in sorted(milestone_groups.items()):
            if milestone == 'No Milestone':
                continue
            sidebar_html.append(f'<details>')
            sidebar_html.append(f'<summary>{html.escape(milestone)} ({len(milestone_issues)})</summary>')
            sidebar_html.append(f'<ul class="nav-list">')
            for issue in sorted(milestone_issues, key=lambda x: x.created_at, reverse=True):
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
    
    # Sort issues by creation date (newest first)
    issues_sorted = sorted(issues, key=lambda x: x.created_at, reverse=True)
    
    # Collect unique labels for filter chips
    all_labels = set()
    for issue in issues:
        for label in issue.labels:
            all_labels.add(label['name'])
    
    # Generate filter chips HTML
    filter_chips = []
    filter_chips.append('<div class="filter-chip" onclick="filterIssues(\"all\")">ALL ISSUES</div>')
    filter_chips.append('<div class="filter-chip" onclick="filterIssues(\"open\")">OPEN</div>')
    filter_chips.append('<div class="filter-chip" onclick="filterIssues(\"closed\")">CLOSED</div>')
    # Add ALL labels as chips (not just common ones) - this replaces the sidebar labels
    for label_name in sorted(all_labels):
        safe_label = html.escape(label_name).replace(' ', '-').replace('/', '-').replace('(', '').replace(')', '').lower()
        filter_chips.append(f'<div class="filter-chip" data-filter="label-{safe_label}" onclick="filterIssues(\"label-{safe_label}\")">{html.escape(label_name).upper()}</div>')
    filter_chips_html = ''.join(filter_chips)
    
    # Render issue cards
    issue_cards = []
    for issue in issues_sorted:
        anchor = f"issue-{issue.number}"
        
        # Labels
        labels_html = generate_labels_html(issue.labels)
        
        # Body content with read more functionality
        body_text = issue.body
        body_html = render_markdown_text(body_text)
        
        # Add read more if body is long
        body_id = f"body-{issue.number}"
        if len(body_text) > 500:  # If body is longer than 500 chars
            body_html = f'<div class="issue-body collapsed" id="{body_id}">{body_html}</div><button class="read-more-btn" onclick="toggleReadMore(\'{body_id}\', this)">READ MORE...</button>'
        else:
            body_html = f'<div class="issue-body">{body_html}</div>'
        
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
        
        issue_card_html = f'''
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
    {body_html}
    {comments_html}
    <div class="back-top"><a href="#top">BACK TO TOP</a></div>
</section>
        '''
        issue_cards.append(issue_card_html)
    
    repo_url = f"https://github.com/{owner}/{repo}"
    
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>GitHub Issues - {html.escape(owner)}/{html.escape(repo)}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html {{ overflow-x: hidden; }}
  body {{ overflow-x: hidden; }}
  
  body {{
    font-family: 'JetBrains Mono', 'SF Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    margin: auto; padding: 0; line-height: 1.4;
    background: #ffffff;
    min-height: 100vh;
    font-weight: bold;
    color: #000000;
  }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 0 1rem; }}
  
  /* Brutalist CSS classes */
  .brutalist-border {{
    border: 4px solid #000000;
  }}
  
  .brutalist-shadow {{
    box-shadow: 8px 8px 0px 0px rgba(0,0,0,1);
  }}
  
  /* Layout with sidebar */
  .page {{ 
    display: block; 
    min-height: 100vh;
    overflow-x: hidden;
    max-width: 1200px;
    margin: 0 auto;
    width: 100%;
    position: relative;
  }}
  
  #sidebar {{
    position: fixed; 
    top: 0; 
    left: 0;
    width: 280px;
    height: 100vh; 
    overflow-y: auto; 
    overflow-x: hidden;
    background: #000000;
    border-right: 4px solid #000000;
    padding: 1rem;
    box-shadow: 8px 0px 0px 0px rgba(0,0,0,1);
    z-index: 1000;
  }}
  
  /* Ensure sidebar stays fixed with custom scrollbar */
  #sidebar::-webkit-scrollbar {{
    width: 8px;
  }}
  #sidebar::-webkit-scrollbar-track {{
    background: #000000;
  }}
  #sidebar::-webkit-scrollbar-thumb {{
    background: #facc15;
    border: 1px solid #000000;
  }}
  #sidebar h3 {{ 
    margin: 1.5rem 0 0.8rem 0; 
    font-size: 0.9rem; 
    color: #ffffff;
    text-transform: uppercase; 
    font-weight: 900;
    letter-spacing: 2px;
    font-family: 'JetBrains Mono', monospace;
  }}
  #sidebar h3:first-child {{ margin-top: 0; }}
  
  .nav-section {{ margin-bottom: 2rem; }}
  .nav-list {{ list-style: none; padding: 0; margin: 0; }}
  .nav-list li {{ margin: 0.5rem 0; }}
  .nav-list a {{ 
    text-decoration: none; 
    color: #ffffff;
    display: block;
    padding: 0.8rem; 
    border: 2px solid #ffffff; 
    font-size: 0.75rem;
    font-weight: bold;
    text-transform: uppercase;
    letter-spacing: 1px;
    background: #000000;
    word-wrap: break-word;
    overflow-wrap: break-word;
    hyphens: auto;
  }}
  .nav-list a:hover {{ 
    background: #ffffff;
    color: #000000;
    transform: translate(2px, 2px);
    box-shadow: none;
  }}
  .nav-list a.open {{ 
    background: #dc2626;
    border-color: #dc2626;
    color: #ffffff;
  }}
  .nav-list a.closed {{ 
    background: #facc15;
    border-color: #facc15;
    color: #000000;
  }}
  
  details {{ margin: 0.8rem 0; }}
  details summary {{ 
    cursor: pointer; 
    font-weight: 900; 
    padding: 0.8rem;
    color: #ffffff;
    border: 2px solid #ffffff;
    background: #000000;
    text-transform: uppercase;
    letter-spacing: 1px;
    font-size: 0.8rem;
  }}
  details summary:hover {{ 
    background: #ffffff;
    color: #000000;
    transform: translate(2px, 2px);
  }}
  
  main.container {{ 
    margin-left: 280px;
    padding: 1rem; 
    background: #ffffff;
    border-left: 4px solid #000000;
    overflow-x: hidden;
    word-wrap: break-word;
    min-width: 0;
    width: auto;
  }}
  
  .header {{ 
    background: #000000;
    border: 4px solid #000000;
    box-shadow: 8px 8px 0px 0px rgba(0,0,0,1);
    padding: 1.5rem;
    margin-bottom: 1.5rem;
    color: #ffffff;
    overflow-x: hidden;
    width: 100%;
  }}
  
  /* Search functionality */
  .search-container {{
    margin-top: 1rem;
    margin-bottom: 1rem;
  }}
  .search-input {{
    width: 100%;
    max-width: 300px;
    padding: 0.8rem;
    border: 4px solid #000000;
    background: #ffffff;
    color: #000000;
    font-family: 'JetBrains Mono', monospace;
    font-weight: bold;
    font-size: 0.8rem;
    text-transform: uppercase;
    box-shadow: 4px 4px 0px 0px rgba(0,0,0,1);
  }}
  .search-input::placeholder {{
    color: #666666;
    text-transform: uppercase;
  }}
  .search-input:focus {{
    outline: none;
    transform: translate(2px, 2px);
    box-shadow: none;
  }}
  .header h1 {{
    font-size: 2rem;
    font-weight: 900;
    margin-bottom: 1rem;
    text-transform: uppercase;
    letter-spacing: 2px;
    color: #ffffff;
    font-family: 'JetBrains Mono', monospace;
    word-wrap: break-word;
  }}
  .repo-info {{ color: #ffffff; font-size: 1rem; font-weight: bold; }}
  .repo-info a {{ color: #facc15; text-decoration: underline; font-weight: bold; }}
  .repo-info a:hover {{ color: #ffffff; background: #facc15; padding: 0 4px; }}
  .stats {{ 
    margin-top: 1rem; 
    display: flex; 
    gap: 0.8rem; 
    flex-wrap: wrap;
    align-items: center;
  }}
  .stat {{ 
    padding: 0.6rem 1rem; 
    background: #ffffff;
    border: 2px solid #000000;
    box-shadow: 4px 4px 0px 0px rgba(0,0,0,1);
    font-size: 0.8rem;
    font-weight: 900;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #000000;
    font-family: 'JetBrains Mono', monospace;
  }}
  .stat.open {{ 
    background: #dc2626;
    color: #ffffff;
    border-color: #dc2626;
  }}
  .stat.closed {{ 
    background: #facc15;
    color: #000000;
    border-color: #facc15;
  }}
  
  /* Filter chips */
  .filter-chips {{
    margin-top: 1rem;
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
    align-items: center;
    overflow-x: auto;
    padding-bottom: 0.5rem;
  }}
  .chips-label {{
    color: #ffffff;
    font-family: 'JetBrains Mono', monospace;
    font-weight: 900;
    font-size: 0.8rem;
    letter-spacing: 1px;
    margin-right: 0.5rem;
    flex-shrink: 0;
  }}
  .filter-chip {{
    padding: 0.4rem 0.8rem;
    background: #facc15;
    border: 2px solid #000000;
    box-shadow: 2px 2px 0px 0px rgba(0,0,0,1);
    font-size: 0.7rem;
    font-weight: bold;
    text-transform: uppercase;
    letter-spacing: 1px;
    cursor: pointer;
    font-family: 'JetBrains Mono', monospace;
    color: #000000;
    white-space: nowrap;
    flex-shrink: 0;
  }}
  .filter-chip:hover {{
    background: #000000;
    color: #ffffff;
    transform: translate(1px, 1px);
    box-shadow: none;
  }}
  .filter-chip.active {{
    background: #000000;
    color: #ffffff;
  }}
  
  /* View toggle */
  .view-toggle {{
    margin: 1.5rem 0;
    display: flex;
    gap: 0.5rem;
    align-items: center;
    justify-content: flex-start;
  }}
  .toggle-btn {{
    padding: 0.8rem 1.2rem;
    border: 4px solid #000000;
    background: #ffffff;
    cursor: pointer;
    font-size: 0.8rem;
    font-weight: 900;
    color: #000000;
    text-transform: uppercase;
    letter-spacing: 1px;
    font-family: 'JetBrains Mono', monospace;
    box-shadow: 4px 4px 0px 0px rgba(0,0,0,1);
  }}
  .toggle-btn.active {{
    background: #000000;
    color: #ffffff;
    transform: translate(2px, 2px);
    box-shadow: none;
  }}
  .toggle-btn:hover:not(.active) {{ 
    background: #facc15;
    transform: translate(2px, 2px);
    box-shadow: none;
  }}
  
  /* Issue cards */
  .issue-card {{
    background: #ffffff;
    border: 4px solid #000000;
    margin-bottom: 1rem; 
    padding: 1.5rem;
    box-shadow: 8px 8px 0px 0px rgba(0,0,0,1);
    position: relative;
    overflow-x: hidden;
    word-wrap: break-word;
    overflow-wrap: break-word;
    hyphens: auto;
  }}
  .issue-card:hover {{
    transform: translate(4px, 4px);
    box-shadow: none;
  }}
  .issue-card.open {{
    border-left: 8px solid #dc2626;
  }}
  .issue-card.closed {{
    border-left: 8px solid #facc15;
  }}
  
  .issue-header h2 {{ 
    margin: 0 0 1rem 0; 
    display: flex; 
    align-items: center; 
    gap: 1rem;
    font-size: 1.2rem;
    flex-wrap: wrap;
    max-width: 100%;
    overflow-x: hidden;
  }}
  .issue-link {{ 
    text-decoration: none; 
    color: #000000; 
    flex: 1;
    font-weight: 900;
    text-transform: uppercase;
    letter-spacing: 1px;
    font-family: 'JetBrains Mono', monospace;
    word-wrap: break-word;
    overflow-wrap: break-word;
    hyphens: auto;
    max-width: 100%;
    min-width: 0;
  }}
  .issue-link:hover {{ 
    background: #000000;
    color: #ffffff;
    padding: 4px 8px;
  }}
  
  .state-badge {{
    font-size: 0.7rem; 
    padding: 0.5rem 0.8rem; 
    white-space: nowrap;
    font-weight: 900;
    text-transform: uppercase;
    letter-spacing: 1px;
    border: 2px solid #000000;
    box-shadow: 2px 2px 0px 0px rgba(0,0,0,1);
    font-family: 'JetBrains Mono', monospace;
  }}
  .state-badge.open {{ 
    background: #dc2626;
    color: #ffffff;
    border-color: #dc2626;
  }}
  .state-badge.closed {{ 
    background: #facc15;
    color: #000000;
    border-color: #facc15;
  }}
  
  .issue-meta {{ 
    color: #000000; 
    font-size: 0.8rem; 
    margin-bottom: 1rem;
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
    font-weight: bold;
    text-transform: uppercase;
    letter-spacing: 1px;
    font-family: 'JetBrains Mono', monospace;
  }}
  .labels {{ margin: 1rem 0; }}
  .label {{ 
    display: inline-block; 
    padding: 0.4rem 0.6rem; 
    font-size: 0.7rem; 
    font-weight: 900;
    margin-right: 0.5rem; 
    margin-bottom: 0.5rem;
    border: 2px solid #000000;
    box-shadow: 2px 2px 0px 0px rgba(0,0,0,1);
    text-transform: uppercase;
    letter-spacing: 1px;
    font-family: 'JetBrains Mono', monospace;
    word-wrap: break-word;
  }}
  .milestone {{ 
    color: #000000; 
    font-size: 0.8rem; 
    margin: 0.8rem 0;
    font-weight: 900;
    padding: 0.5rem 1rem;
    background: #facc15;
    border: 2px solid #000000;
    box-shadow: 2px 2px 0px 0px rgba(0,0,0,1);
    display: inline-block;
    text-transform: uppercase;
    letter-spacing: 1px;
    font-family: 'JetBrains Mono', monospace;
  }}
  
  .issue-body {{ 
    margin: 1rem 0; 
    font-size: 0.9rem;
    line-height: 1.5;
    color: #000000;
    font-weight: bold;
    overflow-x: hidden;
    word-wrap: break-word;
    overflow-wrap: break-word;
    hyphens: auto;
  }}
  .issue-body.collapsed {{
    max-height: 200px;
    overflow: hidden;
    position: relative;
  }}
  .issue-body.collapsed::after {{
    content: '';
    position: absolute;
    bottom: 0;
    left: 0;
    height: 50px;
    width: 100%;
    background: linear-gradient(transparent, #ffffff);
    pointer-events: none;
  }}
  .read-more-btn {{
    background: #facc15;
    border: 2px solid #000000;
    padding: 0.5rem 1rem;
    margin: 0.5rem 0;
    font-family: 'JetBrains Mono', monospace;
    font-weight: 900;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 1px;
    cursor: pointer;
    color: #000000;
    box-shadow: 2px 2px 0px 0px rgba(0,0,0,1);
  }}
  .read-more-btn:hover {{
    background: #000000;
    color: #ffffff;
    transform: translate(1px, 1px);
    box-shadow: none;
  }}
  .issue-body p:first-child {{ margin-top: 0; }}
  .issue-body p:last-child {{ margin-bottom: 0; }}
  .issue-body h1, .issue-body h2, .issue-body h3 {{ 
    color: #000000; 
    margin-top: 1.5rem; 
    margin-bottom: 0.8rem;
    font-weight: 900;
    text-transform: uppercase;
    letter-spacing: 1px;
  }}
  .issue-body ul, .issue-body ol {{ padding-left: 1.5rem; }}
  .issue-body li {{ margin: 0.3rem 0; }}
  .issue-body pre {{ max-width: 100%; overflow-x: auto; }}
  .issue-body code {{ max-width: 100%; overflow-wrap: break-word; }}
  .issue-body img {{ max-width: 100%; height: auto; }}
  
  .comments {{ margin-top: 1.5rem; }}
  .comments h4 {{ 
    color: #000000; 
    border-bottom: 4px solid #000000;
    padding-bottom: 0.5rem;
    font-size: 1rem;
    font-weight: 900;
    text-transform: uppercase;
    letter-spacing: 2px;
    font-family: 'JetBrains Mono', monospace;
  }}
  .comment {{ 
    background: #ffffff;
    border: 2px solid #000000;
    padding: 1rem; 
    margin: 1rem 0;
    box-shadow: 4px 4px 0px 0px rgba(0,0,0,1);
    overflow-x: hidden;
    word-wrap: break-word;
  }}
  .comment-meta {{ 
    color: #000000; 
    font-size: 0.8rem; 
    margin-bottom: 0.5rem;
    font-weight: 900;
    text-transform: uppercase;
    letter-spacing: 1px;
    font-family: 'JetBrains Mono', monospace;
  }}
  
  .back-top {{ 
    margin-top: 1rem; 
    font-size: 0.8rem;
    text-align: center;
  }}
  .back-top a {{ 
    color: #000000; 
    text-decoration: none;
    padding: 0.5rem 1rem;
    background: #facc15;
    border: 2px solid #000000;
    box-shadow: 2px 2px 0px 0px rgba(0,0,0,1);
    font-weight: 900;
    text-transform: uppercase;
    letter-spacing: 1px;
    font-family: 'JetBrains Mono', monospace;
  }}
  .back-top a:hover {{ 
    background: #000000;
    color: #ffffff;
    transform: translate(1px, 1px);
    box-shadow: none;
  }}
  
  /* LLM view */
  #llm-view {{ display: none; }}
  #llm-text {{
    width: 100%;
    height: 70vh;
    font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 0.8em;
    border: 4px solid #000000;
    padding: 1rem;
    resize: vertical;
    background: #ffffff;
    box-shadow: 8px 8px 0px 0px rgba(0,0,0,1);
    font-weight: bold;
    color: #000000;
    overflow-x: hidden;
  }}
  .copy-hint {{
    margin-top: 1rem;
    color: #000000;
    font-size: 0.8rem;
    text-align: center;
    font-weight: 900;
    text-transform: uppercase;
    letter-spacing: 1px;
    font-family: 'JetBrains Mono', monospace;
  }}
  
  /* Code styling */
  pre {{ 
    background: #ffffff;
    padding: 1rem; 
    overflow-x: auto;
    border: 2px solid #000000;
    box-shadow: 4px 4px 0px 0px rgba(0,0,0,1);
    max-width: 100%;
    overflow-wrap: break-word;
  }}
  code {{ 
    font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    background: #facc15; 
    padding: 0.2rem 0.4rem; 
    font-size: 0.8em;
    color: #000000;
    font-weight: bold;
    border: 1px solid #000000;
    word-wrap: break-word;
    overflow-wrap: break-word;
  }}
  pre code {{ background: none; padding: 0; color: #000000; border: none; }}
  
  blockquote {{ 
    border-left: 8px solid #000000; 
    margin: 1rem 0; 
    padding: 1rem; 
    color: #000000;
    background: #facc15;
    border-top: 2px solid #000000;
    border-bottom: 2px solid #000000;
    border-right: 2px solid #000000;
    font-weight: bold;
    box-shadow: 4px 4px 0px 0px rgba(0,0,0,1);
  }}
  
  :target {{ 
    scroll-margin-top: 20px;
    animation: highlight 1s ease-in-out;
  }}
  
  @keyframes highlight {{
    0% {{ background: #facc15; transform: scale(1.02); }}
    100% {{ background: transparent; transform: scale(1); }}
  }}
  
  /* Mobile sidebar toggle button */
  .mobile-menu-toggle {{
    display: none;
    position: fixed;
    top: 1rem;
    left: 1rem;
    z-index: 1001;
    background: #000000;
    color: #ffffff;
    border: 4px solid #000000;
    padding: 0.8rem;
    cursor: pointer;
    font-family: 'JetBrains Mono', monospace;
    font-weight: 900;
    text-transform: uppercase;
    letter-spacing: 1px;
    font-size: 0.8rem;
    box-shadow: 4px 4px 0px 0px rgba(0,0,0,1);
  }}
  .mobile-menu-toggle:hover {{
    background: #facc15;
    color: #000000;
    transform: translate(2px, 2px);
    box-shadow: none;
  }}
  .mobile-menu-toggle.active {{
    background: #facc15;
    color: #000000;
  }}

  /* Sidebar overlay for mobile */
  .sidebar-overlay {{
    display: none;
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.5);
    z-index: 999;
  }}

  /* Responsive design */
  @media (max-width: 1024px) {{
    #sidebar {{ 
      padding: 0.8rem; 
      width: 250px;
    }}
    main.container {{ margin-left: 250px; }}
    .header h1 {{ font-size: 1.8rem; }}
  }}
  
  @media (max-width: 768px) {{
    .mobile-menu-toggle {{ display: block; }}
    
    .page {{ 
      max-width: 100%;
      margin: 0;
    }}
    
    #sidebar {{ 
      position: fixed;
      top: 0;
      left: -300px; /* Hidden by default */
      width: 280px;
      height: 100vh;
      overflow-y: auto;
      background: #000000;
      border-right: 4px solid #000000;
      padding: 4rem 1rem 1rem 1rem; /* Top padding for menu toggle */
      box-shadow: 8px 0px 0px 0px rgba(0,0,0,1);
      z-index: 1000;
      transition: left 0.3s ease-in-out;
    }}
    
    #sidebar.open {{
      left: 0; /* Show sidebar */
    }}
    
    .sidebar-overlay.active {{
      display: block;
    }}
    
    main.container {{
      margin-left: 0;
      width: 100%;
      border-left: none;
      padding: 1rem;
    }}
    
    .header {{ 
      padding: 1rem; 
      padding-top: 4rem; /* Space for menu toggle */
    }}
    .header h1 {{ font-size: 1.6rem; }}
    .stats {{ justify-content: flex-start; }}
    .filter-chips {{ justify-content: flex-start; }}
    .issue-card {{ 
      padding: 1rem;
      margin-bottom: 0.8rem;
    }}
    .issue-header h2 {{ 
      font-size: 1rem;
      flex-direction: column;
      align-items: flex-start;
      gap: 0.5rem;
    }}
    .issue-meta {{ flex-direction: column; gap: 0.3rem; }}
    .nav-list a {{ font-size: 0.7rem; padding: 0.6rem; }}
  }}
  
  @media (max-width: 480px) {{
    .container {{ padding: 0 0.5rem; }}
    #sidebar {{ 
      padding: 4rem 0.8rem 0.8rem 0.8rem;
      width: 260px;
      left: -280px;
    }}
    #sidebar.open {{ left: 0; }}
    main.container {{ padding: 0.8rem; }}
    .header {{ padding: 1rem; padding-top: 4rem; }}
    .header h1 {{ font-size: 1.4rem; }}
    .issue-card {{ padding: 0.8rem; }}
    .toggle-btn {{ 
      padding: 0.5rem 0.8rem;
      font-size: 0.7rem;
    }}
    .filter-chip {{
      padding: 0.3rem 0.6rem;
      font-size: 0.6rem;
    }}
    .stat {{ 
      padding: 0.4rem 0.6rem;
      font-size: 0.7rem;
    }}
    .mobile-menu-toggle {{
      padding: 0.6rem;
      font-size: 0.7rem;
    }}
    * {{ overflow-wrap: break-word; word-wrap: break-word; }}
  }}
</style>
</head>
<body>
<a id="top"></a>

<!-- Mobile menu toggle button -->
<button class="mobile-menu-toggle" onclick="toggleMobileMenu()">☰ MENU</button>

<!-- Sidebar overlay for mobile -->
<div class="sidebar-overlay" onclick="closeMobileMenu()"></div>

<div class="page">
  <nav id="sidebar">
    {sidebar_nav}
  </nav>

  <main class="container">
    <div class="header">
      <h1>GITHUB ISSUES</h1>
      <div class="repo-info">
        <strong>REPOSITORY:</strong> 
        <a href="{repo_url}" target="_blank">{html.escape(owner)}/{html.escape(repo)}</a>
      </div>
      <div class="stats">
        <div class="stat open">{len(open_issues)} OPEN</div>
        <div class="stat closed">{len(closed_issues)} CLOSED</div>
        <div class="stat">{len(issues)} TOTAL</div>
      </div>
      <div class="search-container">
        <input type="text" class="search-input" placeholder="SEARCH ISSUES..." oninput="searchIssues(this.value)" />
      </div>
      <div class="filter-chips">
        <div class="chips-label"><strong>FILTER BY:</strong></div>
        {filter_chips_html}
      </div>
    </div>

    <div class="view-toggle">
      <strong>View:</strong>
      <button class="toggle-btn active" onclick="showHumanView()">HUMAN VIEW</button>
      <button class="toggle-btn" onclick="showLLMView()">LLM VIEW</button>
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

function filterIssues(filterType) {{
  console.log('Filter clicked:', filterType);
  
  // Remove active class from all chips
  document.querySelectorAll('.filter-chip').forEach(chip => {{
    chip.classList.remove('active');
  }});
  
  // Add active class to the clicked chip - use event.target if available
  if (typeof event !== 'undefined' && event.target) {{
    event.target.classList.add('active');
  }}
  
  // Clear search input
  const searchInput = document.querySelector('.search-input');
  if (searchInput) {{
    searchInput.value = '';
  }}
  
  // Get all issue cards
  const issueCards = document.querySelectorAll('.issue-card');
  console.log('Found', issueCards.length, 'issue cards');
  
  let visibleCount = 0;
  
  // Filter the cards
  issueCards.forEach(card => {{
    let shouldShow = false;
    
    if (filterType === 'all') {{
      shouldShow = true;
    }} else if (filterType === 'open') {{
      shouldShow = card.classList.contains('open');
    }} else if (filterType === 'closed') {{
      shouldShow = card.classList.contains('closed');
    }} else if (filterType.startsWith('label-')) {{
      // Extract label name from filter type (remove 'label-' prefix)
      const labelName = filterType.replace('label-', '').toLowerCase().replace(/-/g, ' ');
      const labels = card.querySelectorAll('.label');
      
      labels.forEach(label => {{
        const labelText = label.textContent.toLowerCase().trim();
        if (labelText === labelName || labelText.includes(labelName) || labelName.includes(labelText)) {{
          shouldShow = true;
        }}
      }});
    }}
    
    // Show or hide the card
    if (shouldShow) {{
      card.style.display = 'block';
      visibleCount++;
    }} else {{
      card.style.display = 'none';
    }}
  }});
  
  console.log('Showing', visibleCount, 'out of', issueCards.length, 'cards');
  
  // Update sidebar links
  const sidebarLinks = document.querySelectorAll('.nav-list a');
  sidebarLinks.forEach(link => {{
    const href = link.getAttribute('href');
    if (href && href.startsWith('#')) {{
      const issueCard = document.querySelector(href);
      if (issueCard) {{
        const listItem = link.closest('li');
        if (listItem) {{
          listItem.style.display = issueCard.style.display;
        }}
      }}
    }}
  }});
}}

function searchIssues(searchTerm) {{
  const issueCards = document.querySelectorAll('.issue-card');
  const navLinks = document.querySelectorAll('.nav-list a');
  
  searchTerm = searchTerm.toLowerCase().trim();
  
  issueCards.forEach(card => {{
    let shouldShow = false;
    
    if (searchTerm === '') {{
      shouldShow = true;
    }} else {{
      // Search in title
      const titleElement = card.querySelector('.issue-link');
      if (titleElement && titleElement.textContent.toLowerCase().includes(searchTerm)) {{
        shouldShow = true;
      }}
      
      // Search in issue body
      const bodyElement = card.querySelector('.issue-body');
      if (bodyElement && bodyElement.textContent.toLowerCase().includes(searchTerm)) {{
        shouldShow = true;
      }}
      
      // Search in labels
      const labels = card.querySelectorAll('.label');
      labels.forEach(label => {{
        if (label.textContent.toLowerCase().includes(searchTerm)) {{
          shouldShow = true;
        }}
      }});
      
      // Search in issue number
      const issueNumber = card.id.replace('issue-', '');
      if (issueNumber.includes(searchTerm) || ('#' + issueNumber).includes(searchTerm)) {{
        shouldShow = true;
      }}
    }}
    
    card.style.display = shouldShow ? 'block' : 'none';
  }});
  
  // Update sidebar navigation
  navLinks.forEach(link => {{
    const issueId = link.getAttribute('href').substring(1);
    const issueCard = document.getElementById(issueId);
    if (issueCard) {{
      link.style.display = issueCard.style.display;
    }}
  }});
  
  // Clear active filter chips when searching
  if (searchTerm !== '') {{
    document.querySelectorAll('.filter-chip').forEach(chip => {{
      chip.classList.remove('active');
    }});
  }}
}}

function toggleReadMore(bodyId, button) {{
  const bodyElement = document.getElementById(bodyId);
  const isCollapsed = bodyElement.classList.contains('collapsed');
  
  if (isCollapsed) {{
    bodyElement.classList.remove('collapsed');
    button.textContent = 'READ LESS...';
  }} else {{
    bodyElement.classList.add('collapsed');
    button.textContent = 'READ MORE...';
  }}
}}

// Mobile sidebar functions
function toggleMobileMenu() {{
  console.log('toggleMobileMenu called');
  const sidebar = document.getElementById('sidebar');
  const overlay = document.querySelector('.sidebar-overlay');
  const toggleButton = document.querySelector('.mobile-menu-toggle');
  
  console.log('Elements found:', {{
    sidebar: !!sidebar,
    overlay: !!overlay,
    toggleButton: !!toggleButton
  }});
  
  if (sidebar && overlay && toggleButton) {{
    sidebar.classList.toggle('open');
    overlay.classList.toggle('active');
    toggleButton.classList.toggle('active');
    console.log('Sidebar is now:', sidebar.classList.contains('open') ? 'open' : 'closed');
  }} else {{
    console.error('Missing required elements for mobile menu toggle');
  }}
}}

function closeMobileMenu() {{
  const sidebar = document.getElementById('sidebar');
  const overlay = document.querySelector('.sidebar-overlay');
  const toggleButton = document.querySelector('.mobile-menu-toggle');
  
  sidebar.classList.remove('open');
  overlay.classList.remove('active');
  toggleButton.classList.remove('active');
}}

// Close mobile menu when clicking on a sidebar link
function handleSidebarLinkClick() {{
  // Only close on mobile screens
  if (window.innerWidth <= 768) {{
    closeMobileMenu();
  }}
}}

// Close mobile menu when clicking outside or on a link
document.addEventListener('click', function(e) {{
  const sidebar = document.getElementById('sidebar');
  const toggleButton = document.querySelector('.mobile-menu-toggle');
  
  // Close if clicking outside sidebar and toggle button (only on mobile)
  if (window.innerWidth <= 768 && 
      sidebar.classList.contains('open') && 
      !sidebar.contains(e.target) && 
      !toggleButton.contains(e.target) &&
      !e.target.classList.contains('sidebar-overlay')) {{
    closeMobileMenu();
  }}
}});

// Handle window resize
window.addEventListener('resize', function() {{
  // Close mobile menu if resizing to desktop
  if (window.innerWidth > 768) {{
    closeMobileMenu();
  }}
}});

// Initialize first filter chip as active and add click handlers
document.addEventListener('DOMContentLoaded', function() {{
  console.log('DOM Content Loaded - initializing filters');
  
  // Debug: Check if mobile elements exist
  const mobileToggle = document.querySelector('.mobile-menu-toggle');
  const sidebar = document.getElementById('sidebar');
  const overlay = document.querySelector('.sidebar-overlay');
  
  console.log('Mobile elements check:', {{
    mobileToggle: !!mobileToggle,
    sidebar: !!sidebar,
    overlay: !!overlay
  }});
  
  // Initialize first chip as active
  const firstChip = document.querySelector('.filter-chip');
  if (firstChip) {{
    firstChip.classList.add('active');
    console.log('Set first chip as active:', firstChip.textContent);
  }} else {{
    console.error('No filter chips found!');
  }}
  
  // Add click handlers to sidebar links to close mobile menu
  document.querySelectorAll('#sidebar a').forEach(link => {{
    link.addEventListener('click', handleSidebarLinkClick);
  }});
  
  // Add explicit click handlers to all filter chips as backup
  document.querySelectorAll('.filter-chip').forEach(chip => {{
    chip.addEventListener('click', function(e) {{
      e.preventDefault();
      e.stopPropagation();
      
      // Get filter type from onclick attribute or data-filter attribute
      let filterType = this.getAttribute('data-filter');
      
      if (!filterType) {{
        const onclickAttr = this.getAttribute('onclick');
        if (onclickAttr) {{
          const match = onclickAttr.match(/filterIssues\\([\"']([^\"']+)[\"']\\)/);
          if (match) {{
            filterType = match[1];
          }}
        }}
      }}
      
      if (!filterType) {{
        filterType = 'all';
      }}
      
      console.log('Chip clicked:', this.textContent, 'Filter type:', filterType);
      console.log('Available issue cards:', document.querySelectorAll('.issue-card').length);
      
      // Set global event for filterIssues function
      window.currentEvent = e;
      window.currentTarget = this;
      
      // Call filterIssues function
      filterIssues(filterType);
    }});
  }});
}});
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