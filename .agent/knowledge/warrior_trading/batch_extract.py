#!/usr/bin/env python3
"""
Batch extract transcripts from Warrior Trading YouTube channel.

Usage:
    python batch_extract.py --weeks 1        # Last 1 week
    python batch_extract.py --weeks 2        # Last 2 weeks
    python batch_extract.py --after 2025-12-01 --before 2025-12-31  # Date range
    python batch_extract.py --list-only      # Just list videos, don't extract
    python batch_extract.py --list-only --save-list  # Save list to cache
    python batch_extract.py --use-list       # Use cached list (skip date filtering)
    python batch_extract.py --videos ID1,ID2,ID3     # Extract specific video IDs
"""

import subprocess
import sys
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path


# Warrior Trading channel URL (Ross Cameron's daily recaps)
CHANNEL_URL = "https://www.youtube.com/@DaytradeWarrior/videos"
CACHE_FILE = Path(__file__).parent / ".video_list_cache.json"


def get_channel_videos_with_dates(max_videos: int = 50, after_date: str = None, before_date: str = None) -> list[dict]:
    """Fetch video list with dates from the Warrior Trading channel.
    
    Uses early-exit optimization: since channel videos are in reverse chronological
    order (newest first), we stop once we hit a video before our after_date.
    """
    print(f"Fetching video list from channel (max {max_videos})...")
    
    try:
        # First get list of video IDs quickly
        result = subprocess.run(
            [
                sys.executable, "-m", "yt_dlp",
                "--flat-playlist",
                "--print", "%(id)s|%(title)s",
                "--playlist-end", str(max_videos),
                CHANNEL_URL
            ],
            capture_output=True,
            text=True,
            check=False
        )
        
        video_ids = []
        for line in result.stdout.strip().split('\n'):
            if not line or '|' not in line:
                continue
            parts = line.split('|', 1)
            if len(parts) >= 2:
                video_ids.append({'id': parts[0], 'title': parts[1]})
        
        print(f"  Found {len(video_ids)} videos on channel")
        
        # Now fetch dates for each, with early exit
        videos = []
        skipped_after = 0
        
        print(f"  Checking dates (will stop early if possible)...")
        
        for i, vid in enumerate(video_ids):
            # Get date for this video
            url = f"https://www.youtube.com/watch?v={vid['id']}"
            
            try:
                date_result = subprocess.run(
                    [sys.executable, "-m", "yt_dlp", "--print", "%(upload_date)s", "--no-download", url],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=30
                )
                upload_date = date_result.stdout.strip()
                
                if upload_date and len(upload_date) == 8:
                    parsed_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
                else:
                    continue
                    
            except Exception:
                continue
            
            # Early exit: videos are newest first, so if we hit one before our range, we're done
            if after_date and parsed_date < after_date:
                print(f"    [{i+1}] {parsed_date} - Before range, stopping early")
                break
            
            # Skip if after our range (still checking newer ones)
            if before_date and parsed_date > before_date:
                skipped_after += 1
                continue
            
            # In range!
            print(f"    [{i+1}] {parsed_date} - {vid['title'][:40]}... ✓")
            videos.append({
                'id': vid['id'],
                'title': vid['title'],
                'upload_date': parsed_date,
                'url': url
            })
        
        # Sort by date ascending (oldest first for chronological processing)
        videos.sort(key=lambda x: x['upload_date'])
        
        print(f"  Found {len(videos)} videos in date range")
        if skipped_after > 0:
            print(f"  Skipped {skipped_after} videos after {before_date}")
        
        return videos
    
    except Exception as e:
        print(f"Error fetching channel videos: {e}")
        return []


def get_video_metadata(video_url: str) -> dict:
    """Fetch detailed metadata for a single video (only used as fallback)."""
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "yt_dlp",
                "--dump-json",
                "--no-download",
                video_url
            ],
            capture_output=True,
            text=True,
            check=True
        )
        
        data = json.loads(result.stdout)
        upload_date = data.get('upload_date', '')
        
        # Parse upload date (YYYYMMDD format)
        if upload_date and len(upload_date) == 8:
            parsed_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
        else:
            parsed_date = None
        
        return {
            'id': data.get('id'),
            'title': data.get('title'),
            'upload_date': parsed_date,
            'url': video_url
        }
    
    except Exception as e:
        print(f"  Warning: Could not fetch metadata for {video_url}: {e}")
        return None


def extract_transcript(video_url: str) -> str:
    """Call the existing extract_transcript.py script."""
    script_path = Path(__file__).parent / "extract_transcript.py"
    
    result = subprocess.run(
        [sys.executable, str(script_path), video_url],
        capture_output=True,
        text=True
    )
    
    return result.stdout + result.stderr


def save_list_cache(videos: list[dict]):
    """Save video list to cache file."""
    with open(CACHE_FILE, 'w') as f:
        json.dump({'videos': videos, 'saved_at': datetime.now().isoformat()}, f, indent=2)
    print(f"\nSaved {len(videos)} videos to cache: {CACHE_FILE.name}")


def load_list_cache() -> list[dict]:
    """Load video list from cache file."""
    if not CACHE_FILE.exists():
        print(f"No cache file found: {CACHE_FILE.name}")
        print("Run with --list-only --save-list first to create cache.")
        return []
    
    with open(CACHE_FILE, 'r') as f:
        data = json.load(f)
    
    videos = data.get('videos', [])
    saved_at = data.get('saved_at', 'unknown')
    print(f"Loaded {len(videos)} videos from cache (saved: {saved_at})")
    return videos


def videos_from_ids(video_ids: list[str]) -> list[dict]:
    """Create video list from comma-separated IDs (skip all filtering)."""
    videos = []
    print(f"Processing {len(video_ids)} video IDs directly...")
    
    for vid_id in video_ids:
        vid_id = vid_id.strip()
        if not vid_id:
            continue
        url = f"https://www.youtube.com/watch?v={vid_id}"
        
        # Quick metadata fetch
        try:
            result = subprocess.run(
                [sys.executable, "-m", "yt_dlp", "--print", "%(upload_date)s|%(title)s", "--no-download", url],
                capture_output=True, text=True, check=True, timeout=30
            )
            parts = result.stdout.strip().split('|', 1)
            if len(parts) >= 2:
                upload_date = parts[0]
                title = parts[1]
                parsed_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}" if len(upload_date) == 8 else 'unknown'
                videos.append({'id': vid_id, 'title': title, 'upload_date': parsed_date, 'url': url})
                print(f"  ✓ {parsed_date} - {title[:50]}...")
        except Exception as e:
            print(f"  ✗ {vid_id}: {e}")
    
    return videos


def main():
    parser = argparse.ArgumentParser(description="Batch extract Warrior Trading transcripts")
    parser.add_argument('--weeks', type=int, help='Number of weeks to look back')
    parser.add_argument('--after', type=str, help='Only videos after this date (YYYY-MM-DD)')
    parser.add_argument('--before', type=str, help='Only videos before this date (YYYY-MM-DD)')
    parser.add_argument('--max-videos', type=int, default=50, help='Max videos to scan from channel')
    parser.add_argument('--list-only', action='store_true', help='Just list videos, do not extract')
    parser.add_argument('--save-list', action='store_true', help='Save video list to cache file')
    parser.add_argument('--use-list', action='store_true', help='Use cached list (skip date filtering)')
    parser.add_argument('--videos', type=str, help='Comma-separated video IDs to extract directly')
    
    args = parser.parse_args()
    
    # Calculate date range
    if args.weeks:
        before_date = datetime.now().strftime('%Y-%m-%d')
        after_date = (datetime.now() - timedelta(weeks=args.weeks)).strftime('%Y-%m-%d')
    else:
        after_date = args.after
        before_date = args.before
    
    print(f"\n=== Warrior Trading Batch Transcript Extractor ===")
    
    # Three modes: direct IDs, cached list, or full scan
    if args.videos:
        print(f"Mode: Direct video IDs")
        video_ids = args.videos.split(',')
        videos = videos_from_ids(video_ids)
    elif args.use_list:
        print(f"Mode: Using cached list")
        videos = load_list_cache()
    else:
        print(f"Date range: {after_date or 'any'} to {before_date or 'any'}")
        print()
        videos = get_channel_videos_with_dates(args.max_videos, after_date, before_date)
    
    if not videos:
        print("No videos found!")
        return
    
    print(f"\n{len(videos)} videos to process")
    print()
    
    # List videos
    print("Videos to process (chronological order):")
    print("-" * 60)
    for i, video in enumerate(videos, 1):
        print(f"{i}. [{video['upload_date']}] {video['title'][:50]}")
    print("-" * 60)
    print()
    
    if args.list_only:
        if args.save_list:
            save_list_cache(videos)
        else:
            print("--list-only flag set, not extracting transcripts")
            print("Tip: Add --save-list to cache this list for faster extraction")
        return
    
    # Extract transcripts
    print("Extracting transcripts...")
    print()
    
    extracted_files = []
    for i, video in enumerate(videos, 1):
        print(f"\n[{i}/{len(videos)}] Processing: {video['title'][:50]}...")
        print(f"  URL: {video['url']}")
        
        output = extract_transcript(video['url'])
        print(output)
        
        # Check if file was saved
        if "Saved template to:" in output:
            # Extract filename from output
            for line in output.split('\n'):
                if "Saved template to:" in line:
                    filepath = line.split("Saved template to:")[-1].strip()
                    extracted_files.append({
                        'date': video['upload_date'],
                        'title': video['title'],
                        'file': filepath
                    })
        elif "File already exists" in output:
            print("  (Already exists, skipping)")
    
    # Summary
    print("\n" + "=" * 60)
    print("EXTRACTION COMPLETE")
    print("=" * 60)
    print(f"Total videos processed: {len(videos)}")
    print(f"New transcripts extracted: {len(extracted_files)}")
    print()
    
    if extracted_files:
        print("New files created:")
        for f in extracted_files:
            print(f"  [{f['date']}] {Path(f['file']).name}")
        print()
        print("Next step: Analyze these transcripts with Claude")


if __name__ == "__main__":
    main()
