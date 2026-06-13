import os
from supabase import create_client, Client
from dotenv import load_dotenv
from datetime import datetime, timezone

load_dotenv()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

print(f"Connecting to Supabase: {url[:30]}...")
supabase: Client = create_client(url, key)

print("\n=== DATABASE STATUS ===")
res = supabase.table("predictions").select("*").order("candle_time", desc=True).limit(10).execute()
print(f"\nTotal records found: {len(res.data)}")
print("\nLatest 10 records from DB:")
for r in res.data:
    print(f"Time: {r['candle_time']} | Lower: ${r['lower_bound']:,.2f} | Upper: ${r['upper_bound']:,.2f} | Actual: {r['actual_close']} | Hit: {r['is_hit']}")

now_utc = datetime.now(timezone.utc)
print(f"\nCurrent UTC time: {now_utc.isoformat()}")

# Check for gaps
if res.data:
    latest = datetime.fromisoformat(res.data[0]['candle_time'].replace('Z', '+00:00'))
    gap_hours = (now_utc - latest).total_seconds() / 3600
    print(f"Gap from latest prediction: {gap_hours:.1f} hours")
    
    if gap_hours > 2:
        print(f"\n⚠️  WARNING: Database is {gap_hours:.0f} hours behind!")
        print("   Run 'python tracker.py' to backfill missing data.")
else:
    print("\n⚠️  WARNING: No predictions found in database!")
