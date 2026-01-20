# Warrior Trading Transcript Workflow

Workflow for extracting and analyzing Ross Cameron's Warrior Trading videos.

---

## Location

```
Nexus/.agent/knowledge/warrior_trading/
```

---

## Tools

| Tool | Purpose |
|------|---------|
| `extract_transcript.py` | Single video extraction |
| `batch_extract.py` | Batch extraction from YouTube channel |

---

## Single Video Extraction

```powershell
cd Nexus/.agent/knowledge/warrior_trading
python extract_transcript.py <youtube_url>
```

**Output**: `YYYY-MM-DD_transcript_<video_id>.md`

---

## Batch Extraction Options

```powershell
# Last N weeks
python batch_extract.py --weeks 1
python batch_extract.py --weeks 2

# Date range
python batch_extract.py --after 2025-12-01 --before 2025-12-31

# List only (no extraction)
python batch_extract.py --list-only
python batch_extract.py --list-only --save-list  # Save to cache

# Use cached list (faster)
python batch_extract.py --use-list

# Specific video IDs
python batch_extract.py --videos ID1,ID2,ID3
```

---

## Template Sections

Each transcript file contains:
- **Metadata**: Date, video, stock, P/L
- **Trade Summary**: Entry, catalyst, setup type
- **Setup Criteria**: Why he took the trade
- **Entry/Scaling/Exit Patterns**: Tables and rules
- **Disqualifiers**: What he avoided
- **Key Patterns**: Extracted entry/add/exit/avoid rules
- **Full Transcript**: Collapsible raw text

---

## Key Reference Files

| File | Purpose |
|------|---------|
| `ROSS_RULES_EXTRACTION.md` | Extracted methodology rules |
| `IMPLEMENTATION_AUDIT.md` | Gap analysis vs implementation |
| `README.md` | Index of analysed transcripts |
