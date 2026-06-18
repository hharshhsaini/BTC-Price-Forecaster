# 🤖 GitHub Actions - Automatic Setup Guide

## Problem: Why Manual Backfill Needed?

**Before May 24:** GitHub Actions was running automatically every hour ✅  
**After May 24:** GitHub Actions stopped working ❌

**Reason:** GitHub Actions needs **secrets** to be configured on GitHub.com

---

## ✅ Fix: Enable GitHub Actions (5 minutes)

### Step 1: Push Latest Code to GitHub
```bash
cd /Users/harshsaini/Desktop/btc_forecaster
git push origin main
```

### Step 2: Configure Secrets on GitHub

1. **Go to your GitHub repository:**
   ```
   https://github.com/YOUR_USERNAME/btc_forecaster
   ```

2. **Click on "Settings" tab** (top right)

3. **In left sidebar, click:**
   - Secrets and variables → Actions

4. **Click "New repository secret" button**

5. **Add FIRST secret:**
   - Name: `SUPABASE_URL`
   - Value: `https://jokpqrqaekubwgzznklf.supabase.co`
   - Click "Add secret"

6. **Add SECOND secret:**
   - Name: `SUPABASE_KEY`  
   - Value: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Impva3BxcnFhZWt1Yndnenpua2xmIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Nzk2NjIyNywiZXhwIjoyMDkzNTQyMjI3fQ.J6tEhwBO39NTXVcxx0MkvTowvUYbkOg0gfI8eNtQAMs`
   - Click "Add secret"

### Step 3: Enable Workflow

1. **Go to "Actions" tab** on GitHub

2. **Look for warning:** "Workflows aren't being run on this repository"
   - Click "I understand my workflows, go ahead and enable them"

3. **Find "BTC Forecaster Tracker" workflow**
   - Click on it
   - Click "Enable workflow" (if disabled)

### Step 4: Manual Test Run

1. **In Actions tab, click "BTC Forecaster Tracker"**

2. **Click "Run workflow" dropdown** (top right)

3. **Click green "Run workflow" button**

4. **Wait 1-2 minutes, refresh page**
   - Should see green checkmark ✅ = Success!
   - Red X ❌ = Failed (check logs)

### Step 5: Verify Automatic Runs

1. **Check database after 1 hour:**
   ```bash
   python db_debug.py
   ```
   - Gap should be < 1 hour

2. **Check Actions tab:**
   - New runs should appear every hour at :02 minutes
   - Example: 10:02, 11:02, 12:02, etc.

---

## 🔍 Troubleshooting

### Issue: "Workflow not running automatically"

**Check 1: Workflow enabled?**
```
Actions tab → BTC Forecaster Tracker → Should NOT say "disabled"
```

**Check 2: Secrets configured?**
```
Settings → Secrets and variables → Actions
Should see: SUPABASE_URL, SUPABASE_KEY
```

**Check 3: Recent commits?**
```bash
# Cron jobs only run if repo has commits in last 60 days
git log -1
```

**Fix:** Make a dummy commit if needed:
```bash
echo "# Update" >> README.md
git add README.md
git commit -m "Keep repo active"
git push origin main
```

### Issue: "Workflow runs but fails"

**Check logs:**
1. Actions tab → Click failed run
2. Click "run-tracker" job
3. Expand "Run Tracker" step
4. Read error message

**Common errors:**
- `Missing Supabase credentials` → Secrets not configured
- `Connection refused` → Supabase project paused/deleted
- `Module not found` → requirements.txt issue

---

## 🎯 Expected Behavior (After Fix)

### Automatic Schedule:
- **Every hour at :02 minutes** (e.g., 10:02, 11:02, 12:02)
- Runs automatically via GitHub Actions
- No manual intervention needed

### What Happens Each Hour:
1. **:00-:01** - Binance closes 1-hour candle
2. **:02** - GitHub Actions triggers
3. **:02-:03** - Tracker runs:
   - Fetches latest candles from Binance
   - Evaluates pending predictions (fills actual_close)
   - Generates new prediction for next hour
   - Saves to Supabase database
4. **:03+** - Dashboard shows updated data

### Dashboard Updates:
- **Every 10 seconds** - Page auto-refreshes
- **Every 5 seconds** - Cache refreshes from database
- Real-time: Current price updates continuously

---

## 📊 Verify It's Working

### Test 1: Check Last Run
```bash
# On GitHub: Actions tab
# Should see runs every hour
# Latest run should be < 1 hour ago
```

### Test 2: Check Database
```bash
python db_debug.py

# Expected output:
# ✓ Latest prediction: [current hour]
# ✓ Gap: < 1 hour
# ✓ No warnings
```

### Test 3: Wait for Next Hour
1. Note current time (e.g., 10:45)
2. Wait until :02 of next hour (11:02)
3. Refresh GitHub Actions tab
4. Should see new run started at 11:02
5. Run `python db_debug.py` at 11:05
6. Should see prediction for 11:00 hour

---

## 🆘 If GitHub Actions Still Not Working

### Alternative: Local Cron Job

**For Mac/Linux:**
```bash
# Open crontab editor
crontab -e

# Add this line (runs every hour at :05)
5 * * * * cd /Users/harshsaini/Desktop/btc_forecaster && /usr/bin/python3 manual_backfill.py >> /tmp/btc_tracker.log 2>&1

# Save and exit
# Verify: crontab -l
```

**For Windows:**
```
Use Task Scheduler:
1. Open Task Scheduler
2. Create Basic Task
3. Name: "BTC Forecaster"
4. Trigger: Daily, repeat every 1 hour
5. Action: Start a program
   - Program: python
   - Arguments: manual_backfill.py
   - Start in: C:\path\to\btc_forecaster
6. Finish
```

---

## 🎉 Success Checklist

After setup, verify:
- ✅ GitHub Actions tab shows green checkmarks
- ✅ New workflow runs appear every hour
- ✅ `db_debug.py` shows gap < 1 hour
- ✅ Dashboard history shows recent HIT/MISS
- ✅ No manual `manual_backfill.py` needed
- ✅ System runs 24/7 automatically

---

## 📞 Quick Commands

```bash
# Check if automation is working
python db_debug.py

# If gap > 2 hours (emergency fix)
python manual_backfill.py

# Check GitHub Actions status (on GitHub.com)
# Actions tab → Should see hourly runs

# Force a manual run right now (on GitHub.com)
# Actions → BTC Forecaster Tracker → Run workflow
```

---

**After this setup, system will work exactly like it did before May 24 - fully automated!** 🚀
