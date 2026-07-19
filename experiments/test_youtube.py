import yt_dlp
import json

def search_youtube_metadata(query, max_results=5):
    # The 'ytsearchN:' prefix tells yt-dlp to search YouTube and limit to N results
    search_query = f"ytsearch{max_results}:{query}"
    
    # Configuration options for metadata extraction
    ydl_opts = {
        'extract_flat': False,       # False forces yt-dlp to extract full video metadata, not just the search page preview
        'skip_download': True,       # We only want metadata, do not download the video
        'quiet': True,               # Suppress console output from yt-dlp
        'writesubtitles': True,      # Fetch manual subtitle metadata
        'writeautomaticsub': True,   # Fetch auto-generated subtitle metadata
        'no_warnings': True
    }

    results_metadata = []

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            # extract_info grabs the full dictionary of data
            info_dict = ydl.extract_info(search_query, download=False)
            
            # The 'entries' key contains the search results
            if 'entries' in info_dict:
                for entry in info_dict['entries']:
                    if entry:
                        results_metadata.append(entry)
                        
        except Exception as e:
            print(f"An error occurred during extraction: {e}")

    return results_metadata

if __name__ == "__main__":
    search_term = "Python web scraping tutorial"
    print(f"Searching YouTube for: '{search_term}'...\n")
    
    # Fetch top 2 results to keep the output manageable
    video_data = search_youtube_metadata(search_term, max_results=2)
    
    for index, video in enumerate(video_data):
        print(f"--- Result {index + 1}: {video.get('title')} ---")
        print(f"URL: {video.get('webpage_url')}")
        print(f"Duration: {video.get('duration')} seconds")
        print(f"Channel: {video.get('uploader')} ({video.get('channel_follower_count')} subscribers)")
        print(f"Views: {video.get('view_count')} | Likes: {video.get('like_count')}")
        
        # 1. Description
        desc = video.get('description', '')
        print(f"\nDescription Snippet:\n{desc[:150]}...\n")
        
        # 2. Chapters (Parts of the video)
        chapters = video.get('chapters')
        if chapters:
            print(f"Chapters ({len(chapters)} found):")
            for chapter in chapters:
                print(f"  - [{chapter.get('start_time')}s to {chapter.get('end_time')}s] {chapter.get('title')}")
        else:
            print("Chapters: None defined by creator.")
            
        # 3. Subtitles
        manual_subs = video.get('subtitles', {})
        auto_subs = video.get('automatic_captions', {})
        
        print(f"\nManual Subtitles Available: {list(manual_subs.keys()) if manual_subs else 'None'}")
        
        # Auto-captions usually return dozens of languages, so we'll just slice the first 5 for the printout
        auto_sub_langs = list(auto_subs.keys())
        print(f"Auto Subtitles Available: {auto_sub_langs[:5]} ... (and {len(auto_sub_langs) - 5} more)")
        
        # 4. Tags & Categories
        print(f"\nTags: {video.get('tags', [])[:5]}...")
        print(f"Categories: {video.get('categories', [])}")
        print("="*60 + "\n")
        
        # Note: If you want to dump EVERYTHING to a file to see all available fields:
        # with open(f"video_{index}.json", "w", encoding="utf-8") as f:
        #     json.dump(video, f, indent=4)