---
name: web_search
description: Search the web using DuckDuckGo and return top results
parameters:
  type: object
  properties:
    query:
      type: string
      description: Search query
    num_results:
      type: integer
      description: Number of results to return (default 5, max 10)
      default: 5
  required:
    - query
metadata:
  type: cli
  command_template: "python3 -c 'from ddgs import DDGS; ...'"
  tier: common
  priority: 6
  retry_policy:
    maximum_attempts: 3
    backoff_coefficient: 2.0
---

# Web Search

Search the web using DuckDuckGo and retrieve top results with titles, snippets, and URLs.

## Usage

Use this tool when you need to find current information, documentation, answers, news, or any information from the web.

## Examples

```python
# Find recent news
web_search(query="latest AI developments 2026", num_results=5)

# Look up documentation
web_search(query="Python asyncio tutorial", num_results=3)

# Research a topic
web_search(query="temporal workflow patterns best practices")

# Find specific site
web_search(query="site:github.com temporal python examples")

# Technical question
web_search(query="how to handle retry logic in temporal workflows")
```

## Search Operators

- **Exact phrase**: Use quotes `"exact phrase"`
- **Site search**: `site:example.com query`
- **Exclude**: `-keyword` to exclude results
- **OR search**: `query1 OR query2`
- **File type**: `filetype:pdf query`

## Result Format

Each result includes:
- **Title**: Page title
- **URL**: Link to page
- **Snippet**: Brief description/excerpt
- **Date**: Publication date (if available)

## Notes

- Powered by DuckDuckGo (privacy-focused, no tracking)
- Results are current as of search time
- Default returns 5 results, maximum 10
- Results may be rate-limited on high volume
- Some results may be behind paywalls or require login
- Use specific, detailed queries for better results

## Common Use Cases

- Finding documentation for libraries/frameworks
- Researching technical solutions
- Getting current news or events
- Looking up API references
- Finding code examples
- Fact-checking information
- Discovering tools and resources

## Privacy

- DuckDuckGo does not track searches
- No personal information collected
- Results are not personalized
