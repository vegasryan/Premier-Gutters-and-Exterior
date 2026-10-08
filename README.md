# Premier Gutters and Exterior

This repo deploys to Netlify (site premier-gutters-and-exterior, https://premier-gutters-and-exterior.netlify.app),
from the root of `main`, with no build step (netlify.toml). Push the finished site's files here and Netlify publishes
them.

**Now (8 Oct 2026): the new site, every page**, to show DeeAnn. It is the v2 MVP
(~/Desktop/Premier Gutters v2, http://premier-gutters-v2.idea.localhost:8787/) less the MVP's own tools, with the header's links working
and the 404 at the root. Every page is noindex (this is a preview, not the launch: the launch build with its sitemap, canonical
addresses and robots is deploy/production/ in that project).

Written by `deploy/netlify-home/ship.py --all --push` in that project; don't edit these files by hand. Its pushes carry `[skip netlify]`
unless run with `--netlify`, so the repo can be ahead of the live Netlify site (a production deploy costs 15 credits).

The first site's files are in this repo's history (before 4 Oct), and its source is ~/Desktop/DeeAnn Gutters
(site/production/export.py).
