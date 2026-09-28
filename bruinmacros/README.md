# BruinMacros

Dining hall menus with calories and macros, plus a tap-to-log food tracker.
**Unofficial student project, not affiliated with or endorsed by UCLA.**

## How it works

```
UCLA Dining website ──(hourly)──▶ scraper (GitHub Actions) ──▶ data/menus/*.json ──▶ website (GitHub Pages)
                                                                                       │
                                                               each person's log saved in their own browser
```

- **`scraper/scrape.py`** visits every dining location's page for today and tomorrow,
  reads each meal, station and item, and looks up nutrition on each item's page.
  Nutrition is cached in `data/recipes.json`, so each item is only looked up once a month.
  If a page shows the wrong day, the scraper keeps the last good menu instead of publishing a stale one.
- **`.github/workflows/update-menus.yml`** runs the scraper every hour from about 6am to 10pm
  Los Angeles time, saves any changes, and republishes the site.
- **`index.html`** is the whole website. It loads the menu files and keeps each visitor's
  log in their own browser (nothing is sent anywhere). Visitors can back up and restore their log.

Everything here is free: public GitHub repositories get GitHub Actions and GitHub Pages at no cost.

## Put it online (about 20 minutes)

1. **Make a GitHub account** at <https://github.com/signup> if you don't have one.
2. **Create the repository.** Click **+** (top right) → **New repository**.
   Name it `bruinmacros`, set it to **Public**, and don't add a README. Click **Create repository**.
3. **Upload the files.** On the new repository's page click **uploading an existing file**,
   then drag in everything from this folder, including the hidden `.github` folder.
   On a Mac, press **Cmd + Shift + .** in Finder to show hidden folders. Click **Commit changes**.
   Check that `.github/workflows/update-menus.yml` appears in the repository; the schedule depends on it.
4. **Turn on the website.** **Settings → Pages →** under *Build and deployment*, set **Source** to **GitHub Actions**.
5. **Add your contact email** so UCLA Dining can reach you about the bot:
   **Settings → Secrets and variables → Actions → Variables tab → New repository variable.**
   Name `CONTACT_EMAIL`, value your email.
6. **Run it once now.** **Actions** tab → **Update menus and publish site** → **Run workflow**.
   It takes a few minutes the first time (it looks up nutrition for every item).
7. **Open your site** at `https://YOUR-USERNAME.github.io/bruinmacros/`.
   On your phone, use **Share → Add to Home Screen** so it opens like an app.

After that it runs by itself every hour.

## Checking on it

- The **Actions** tab lists every run. Green is fine.
- A **yellow warning** saying no menu items were found usually means UCLA changed their page layout.
  Open that run, download **raw-pages** under *Artifacts*, and use those pages to update `parse_menu` in the scraper.
- GitHub pauses scheduled workflows in repositories with no activity for 60 days. The hourly menu
  commits should count as activity, but if runs stop, re-enable the workflow on the Actions tab.

## Run it on your own computer (optional)

```
pip install -r scraper/requirements.txt
python scraper/scrape.py          # today and tomorrow
python -m http.server 8000        # then open http://localhost:8000
python -m pytest scraper/tests    # parser tests
```

## Being a good neighbour

- The scraper checks at most hourly, waits between requests, fetches nutrition only for new items,
  and identifies itself with your contact email.
- UCLA Dining's robots.txt only blocks its admin area. UCLA's name and "Bruin" are UCLA trademarks
  (UCLA Policy 110), so keep the "unofficial" notice, don't use UCLA logos, and consider asking UCLA for
  permission to use the name.
- Nutrition numbers come straight from UCLA Dining's pages and can be wrong. The footer tells people to
  check allergens with dining staff; keep it.
