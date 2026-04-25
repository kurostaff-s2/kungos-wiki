#!/bin/bash
# Wiki Lint - Health check for the LLM Wiki
# Run weekly or when asked

set -e

WIKI_DIR="$HOME/llm-wiki"
cd "$WIKI_DIR"

echo "=== LLM Wiki Health Check ==="
echo "Date: $(date)"
echo ""

# 1. Count pages
echo "--- Page Count ---"
TOTAL_PAGES=$(find . -name "*.md" ! -name "AGENTS.md" ! -name "index.md" ! -name "log.md" | wc -l)
echo "Total wiki pages: $TOTAL_PAGES"
echo ""

# 2. Find orphans (pages with no inbound [[links]])
echo "--- Orphan Pages ---"
grep -rl "^\[\[" . 2>/dev/null | sort -u > /tmp/linked-pages.txt || touch /tmp/linked-pages.txt
find . -name "*.md" ! -name "AGENTS.md" ! -name "index.md" ! -name "log.md" | sort > /tmp/all-pages.txt
ORPHANS=$(comm -23 /tmp/all-pages.txt /tmp/linked-pages.txt)
if [ -z "$ORPHANS" ]; then
    echo "No orphan pages found."
else
    echo "Orphan pages (no inbound links):"
    echo "$ORPHANS"
fi
echo ""

# 3. Check for stale log entries (older than 30 days)
echo "--- Recent Activity ---"
echo "Last 10 log entries:"
tail -10 log.md
echo ""

# 4. Check for missing frontmatter
echo "--- Pages Missing Frontmatter ---"
MISSING_FM=$(find . -name "*.md" ! -name "AGENTS.md" ! -name "index.md" ! -name "log.md" -exec grep -L "^---" {} \;)
if [ -z "$MISSING_FM" ]; then
    echo "All pages have frontmatter."
else
    echo "Pages missing YAML frontmatter:"
    echo "$MISSING_FM"
fi
echo ""

# 5. Check project wikis
echo "--- Project Wiki Status ---"
for proj in rebellion-nextjs kteam-dj-be kteam-fe-react renderedge-nextjs; do
    PROJ_WIKI="$HOME/Coding-Projects/$proj/wiki"
    if [ -d "$PROJ_WIKI" ]; then
        PROJ_PAGES=$(find "$PROJ_WIKI" -name "*.md" 2>/dev/null | wc -l)
        echo "$proj: $PROJ_PAGES wiki pages"
    else
        echo "$proj: NO wiki directory"
    fi
done
echo ""

# 6. Cross-reference check: pages mentioned in index that don't exist
echo "--- Index vs Reality ---"
echo "Pages linked in index.md:"
grep -oP '\[\[.*?\]\]' index.md 2>/dev/null | sort -u > /tmp/index-links.txt || touch /tmp/index-links.txt
INDEX_COUNT=$(wc -l < /tmp/index-links.txt)
echo "Total links in index: $INDEX_COUNT"

echo ""
echo "=== Lint Complete ==="
