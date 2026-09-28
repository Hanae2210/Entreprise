# Entreprise

Web crawling with [crawl4ai](https://github.com/unclecode/crawl4ai): turn web pages into clean Markdown for LLM use.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
crawl4ai-setup      # installs the Playwright browser crawl4ai uses
crawl4ai-doctor     # optional: verifies the installation
```

## Usage

```bash
python crawl.py https://example.com https://docs.python.org/3/ -o output
```

Each page is saved as `output/<host_path>.md`. The script exits with status 1 if any URL fails.
