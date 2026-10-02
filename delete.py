import requests
import time

# ==========================================
# INSERT YOUR PAGE ACCESS TOKEN HERE
# ==========================================
PAGE_TOKEN = os.environ.get("FB_TOKEN")

def delete_all_posts():
    print("🚨 WARNING: This script will PERMANENTLY DELETE posts on your Facebook Page.")
    print("This includes bot posts and manual posts. They cannot be recovered.")
    
    # Safety check before running
    confirm = input("\nType 'YES' (all caps) to confirm deletion: ")
    if confirm != "YES":
        print("Operation cancelled. No posts were deleted.")
        return

    print("\n🔄 Connecting to Facebook Graph API...")
    
    # Initial API endpoint to get page posts
    url = "https://graph.facebook.com/v19.0/me/posts"
    params = {
        "access_token": PAGE_TOKEN,
        "limit": 50  # Max number of posts to fetch per request
    }
    
    deleted_count = 0
    
    while url:
        # Fetch a batch of posts
        response = requests.get(url, params=params).json()
        
        # Check for token or permission errors
        if 'error' in response:
            print(f"\n❌ API Error: {response['error']['message']}")
            break
            
        posts = response.get('data', [])
        
        # If the page has no more posts, stop the loop
        if not posts:
            print("\n✅ No more posts found on the page.")
            break
            
        # Loop through the fetched posts and delete them
        for post in posts:
            post_id = post['id']
            delete_url = f"https://graph.facebook.com/v19.0/{post_id}"
            
            # Send the DELETE request
            del_response = requests.delete(delete_url, params={"access_token": PAGE_TOKEN}).json()
            
            if del_response.get('success'):
                deleted_count += 1
                print(f"🗑️ Deleted post ID: {post_id}")
            else:
                print(f"⚠️ Failed to delete {post_id}. Error: {del_response}")
            
            time.sleep(1)
            
        # Get the URL for the next batch of older posts (Pagination)
        url = response.get('paging', {}).get('next')
        # Clear params because the 'next' URL already includes the access_token and limit
        params = {} 

    print(f"\n🏁 Finished! Successfully deleted {deleted_count} posts.")

if __name__ == "__main__":
    delete_all_posts()