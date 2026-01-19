"""
YouTube Transcript Extractor for Warrior Trading Videos

Usage:
    python extract_transcript.py <youtube_url>
    python extract_transcript.py https://www.youtube.com/watch?v=lneGXw0sxzo

Requirements:
    pip install youtube-transcript-api yt-dlp
"""

import sys
import re
import subprocess
import json
from datetime import datetime
from pathlib import Path

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:
    print("Error: youtube-transcript-api not installed")
    print("Run: pip install youtube-transcript-api yt-dlp")
    sys.exit(1)


def get_video_publish_date(url: str) -> tuple[str, str]:
    """Fetch video publish date and title from YouTube using yt-dlp.
    
    Returns:
        tuple: (date_str in YYYY-MM-DD format, video_title)
    """
    try:
        # Use python -m yt_dlp to ensure we use the venv's installation
        result = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--dump-json", "--no-download", url],
            capture_output=True,
            text=True,
            check=True
        )
        metadata = json.loads(result.stdout)
        
        # upload_date is in YYYYMMDD format
        upload_date = metadata.get("upload_date", "")
        if upload_date and len(upload_date) == 8:
            formatted_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
        else:
            # Fallback to current date if not available
            formatted_date = datetime.now().strftime("%Y-%m-%d")
            
        title = metadata.get("title", "Unknown Title")
        return formatted_date, title
        
    except subprocess.CalledProcessError as e:
        print(f"Warning: Could not fetch video metadata: {e}")
        print(f"  stderr: {e.stderr}")
        return datetime.now().strftime("%Y-%m-%d"), "Unknown Title"
    except FileNotFoundError:
        print("Warning: yt-dlp not found. Install with: pip install yt-dlp")
        return datetime.now().strftime("%Y-%m-%d"), "Unknown Title"
    except json.JSONDecodeError as e:
        print(f"Warning: Could not parse video metadata: {e}")
        return datetime.now().strftime("%Y-%m-%d"), "Unknown Title"


def extract_video_id(url: str) -> str:
    """Extract video ID from YouTube URL."""
    patterns = [
        r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:embed/)([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(f"Could not extract video ID from: {url}")


def get_transcript(video_id: str) -> str:
    """Fetch and format transcript from YouTube."""
    try:
        # New API: use .fetch() method on the class
        ytt_api = YouTubeTranscriptApi()
        transcript = ytt_api.fetch(video_id)
        
        # Combine all text segments
        full_text = []
        for entry in transcript:
            text = entry.text.strip()
            if text:
                full_text.append(text)
        
        return ' '.join(full_text)
    except Exception as e:
        raise RuntimeError(f"Failed to get transcript: {e}")


def create_template(url: str, transcript: str, publish_date: str, video_title: str) -> str:
    """Create a markdown template for the transcript.
    
    Args:
        url: YouTube video URL
        transcript: Full transcript text
        publish_date: Video publish date in YYYY-MM-DD format
        video_title: Title of the video from YouTube
    """
    template = f"""# {video_title}

**Date:** {publish_date}  
**Video:** [{video_title}]({url})  
**Stock:** [TICKER]  
**Result:** [P/L]

---

## Trade Summary

| Metric | Value |
|--------|-------|
| Entry | $ |
| Peak | $ |
| Catalyst | |
| Setup Type | |
| Exchange | |
| Alert Time | |

---

## Setup Criteria (Why He Took It)

1. 
2. 
3. 

---

## Entry Pattern

```
[Describe the entry sequence]
```

---

## Scaling Pattern (Adds & Exits)

| Action | Price | Trigger |
|--------|-------|---------|
| Entry | $ | |
| | | |

---

## Exit Criteria

- 
- 

---

## Disqualifiers (What He Avoided)

| Stock | Reason |
|-------|--------|
| | |

---

## Key Patterns Extracted

### Entry Rules
1. 

### Add Rules
1. 

### Exit Rules
1. 

### Avoid Rules
1. 

---

## Full Transcript

<details>
<summary>Click to expand full transcript</summary>

{transcript}

</details>
"""
    return template


def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_transcript.py <youtube_url>")
        print("Example: python extract_transcript.py https://www.youtube.com/watch?v=lneGXw0sxzo")
        sys.exit(1)
    
    url = sys.argv[1]
    
    print(f"Extracting transcript from: {url}")
    
    try:
        video_id = extract_video_id(url)
        print(f"Video ID: {video_id}")
        
        # Fetch publish date and title from YouTube
        print("Fetching video metadata...")
        publish_date, video_title = get_video_publish_date(url)
        print(f"Video title: {video_title}")
        print(f"Publish date: {publish_date}")
        
        transcript = get_transcript(video_id)
        print(f"Transcript length: {len(transcript)} characters")
        
        # Generate template with publish date and title
        template = create_template(url, transcript, publish_date, video_title)
        
        # Save to file with publish date prefix for sorting
        output_file = Path(__file__).parent / f"{publish_date}_transcript_{video_id}.md"
        
        # Safety check: don't overwrite existing files
        if output_file.exists():
            print(f"\nWarning: File already exists: {output_file}")
            print("Use --force to overwrite, or delete the file first.")
            
            # Check for --force flag
            if "--force" not in sys.argv:
                print("Aborting to prevent data loss.")
                sys.exit(0)
            else:
                print("--force flag detected, overwriting...")
        
        output_file.write_text(template, encoding='utf-8')
        
        print(f"\nSaved template to: {output_file}")
        print("\nNext steps:")
        print("1. Fill in the trade summary and analysis")
        print("2. Optionally rename the file to match the pattern: <ticker>_<theme>.md")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
