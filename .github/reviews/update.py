#!/usr/bin/env python3
"""Keeps "5.0 from 36 Google reviews" on the live site in step with her Google Business Profile (Vegas, 9 Nov 2026:
"find out how we can automatically update the google review count on the site when new reviews come in", then "set that up").

The live site's repo (github.com/vegasryan/Premier-Gutters-and-Exterior) carries this file at .github/reviews/update.py, the count at
.github/reviews/reviews.json, and the daily job at .github/workflows/google-reviews.yml. deploy/netlify-home/ship.py copies this file
there on every push and keeps the repo's reviews.json, so the repo's count always wins over the 36 typed into content/pages.json.

    python3 update.py check <dir>     read the count from the Business Profile API; if it changed, write reviews.json and stamp every page
                                      in <dir>. The daily GitHub job runs this. Without the four GBP_* secrets it says so and does nothing.
    python3 update.py stamp <dir>     stamp the pages in <dir> with <dir>/.github/reviews/reviews.json (ship.py runs this on its clone)
    python3 update.py stamp <dir> --count 37 --rating 5.0     the same with given numbers (a test; reviews.json is left alone)

What gets stamped: every "<b>5.0</b> from 36 Google reviews" (and <strong>, and the plain "5.0 from 36 Google reviews" in meta descriptions,
JSON-LD and llms.txt) in the site's .html, .txt, .xml and .json files. Nothing else on the page names the count. It stops if it finds none.

The API: Business Profile API v4 accounts.locations.reviews.list, which answers totalReviewCount and averageRating. It needs Google's
allowlisting of the Cloud project premier-gutters-reviews (project number 967874129116, case 5-0271000041528, 9 Nov 2026) and an OAuth
login from a manager of her profile (elvegasryan@gmail.com). Secrets: GBP_CLIENT_ID, GBP_CLIENT_SECRET, GBP_REFRESH_TOKEN, GBP_LOCATION
("accounts/<id>/locations/<id>"); connect.py sets them. Python standard library only, so the job needs no installs.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

PATTERN = re.compile(r'(<(b|strong)>)?\d\.\d(</(?:b|strong)>)? from \d+ Google reviews')
TEXT_SUFFIXES = {'.html', '.txt', '.xml', '.json'}
SKIP_DIRS = {'.git', '.github', 'node_modules'}
MAX_DROP = 3   # a fall of more than this many reviews in a day is more likely an API fault than real; the job fails and GitHub emails Vegas
KEEPALIVE_DAYS = 50   # GitHub turns off a public repo's scheduled jobs after 60 days with no commit


def rating_text(avg):
    """Google shows one decimal: 4.97 is 5.0, 4.94 is 4.9."""
    return str(Decimal(str(avg)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))


def stamp(site, count, rating):
    """Writes the count and rating into every page of site/. Returns (files changed, places found)."""
    def repl(m):
        tag = m.group(2)
        num = f'<{tag}>{rating}</{tag}>' if tag else rating
        return f'{num} from {count} Google reviews'
    changed = found = 0
    for p in sorted(Path(site).rglob('*')):
        if p.suffix not in TEXT_SUFFIXES or not p.is_file() or SKIP_DIRS & set(p.relative_to(site).parts):
            continue
        text = p.read_text(encoding='utf-8')
        new, n = PATTERN.subn(repl, text)
        found += n
        if new != text:
            p.write_text(new, encoding='utf-8')
            changed += 1
    if found == 0:
        sys.exit(f'stamp: no "from N Google reviews" anywhere in {site}; the markup changed, so update PATTERN in update.py')
    return changed, found


def data_file(site):
    return Path(site) / '.github' / 'reviews' / 'reviews.json'


def read_data(site):
    return json.loads(data_file(site).read_text(encoding='utf-8'))


def post_form(url, fields):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode(), method='POST')
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def get_json(url, token):
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors='replace')[:600]
        if e.code in (403, 429) and ('quota' in body.lower() or 'RATE_LIMIT' in body or 'has not been used' in body):
            sys.exit(f'Google said {e.code}: the project is not allowlisted yet (quota 0) or the v4 API is off. {body}')
        sys.exit(f'Google said {e.code} for {url}: {body}')


def access_token():
    return post_form('https://oauth2.googleapis.com/token', {
        'client_id': os.environ['GBP_CLIENT_ID'], 'client_secret': os.environ['GBP_CLIENT_SECRET'],
        'refresh_token': os.environ['GBP_REFRESH_TOKEN'], 'grant_type': 'refresh_token'})['access_token']


def from_google():
    loc = os.environ['GBP_LOCATION'].strip().strip('/')
    data = get_json(f'https://mybusiness.googleapis.com/v4/{loc}/reviews?pageSize=1', access_token())
    count, avg = data.get('totalReviewCount'), data.get('averageRating')
    if not isinstance(count, int) or count < 1 or avg is None or not 1 <= float(avg) <= 5:
        sys.exit(f'unexpected answer from Google: totalReviewCount={count!r} averageRating={avg!r}')
    return count, rating_text(avg)


def output(**kw):
    """Hands values to the next steps of the GitHub job (and prints them)."""
    out = os.environ.get('GITHUB_OUTPUT')
    for k, v in kw.items():
        print(f'{k}={v}')
        if out:
            with open(out, 'a', encoding='utf-8') as f:
                f.write(f'{k}={v}\n')


def last_commit_age_days(site):
    r = subprocess.run(['git', '-C', str(site), 'log', '-1', '--format=%ct'], capture_output=True, text=True)
    return (time.time() - int(r.stdout.strip())) / 86400 if r.returncode == 0 and r.stdout.strip() else 0


def check(site):
    missing = [k for k in ('GBP_CLIENT_ID', 'GBP_CLIENT_SECRET', 'GBP_REFRESH_TOKEN', 'GBP_LOCATION') if not os.environ.get(k)]
    if missing:
        print(f'not connected yet (no {", ".join(missing)}); nothing to do. See deploy/google-reviews/README.md in the project.')
        output(commit='false')
        return
    old = read_data(site)
    count, rating = from_google()
    today = time.strftime('%Y-%m-%d', time.gmtime())
    if count == old['count'] and rating == old['rating']:
        print(f'no change: {rating} from {count} Google reviews')
        if last_commit_age_days(site) > KEEPALIVE_DAYS:   # one quiet commit, so GitHub keeps the daily job switched on
            old['checked'] = today
            data_file(site).write_text(json.dumps(old, indent=2) + '\n', encoding='utf-8')
            output(commit='true', message=f'Google reviews: still {rating} from {count}, checked {today} (keeps the daily job on) [skip netlify]')
        else:
            output(commit='false')
        return
    if old['count'] - count > MAX_DROP:
        sys.exit(f'the count fell from {old["count"]} to {count} in one day; not publishing it. Check her profile, then run the job again '
                 f'or set reviews.json by hand.')
    changed, found = stamp(site, count, rating)
    data_file(site).write_text(json.dumps({'count': count, 'rating': rating, 'checked': today,
                                           'from': 'Business Profile API, the daily job'}, indent=2) + '\n', encoding='utf-8')
    print(f'{old["rating"]} from {old["count"]} -> {rating} from {count}: {found} places in {changed} files')
    output(commit='true', message=f'Google reviews: {rating} from {count} (was {old["rating"]} from {old["count"]})')


if __name__ == '__main__':
    if len(sys.argv) < 3 or sys.argv[1] not in ('check', 'stamp'):
        sys.exit(__doc__)
    site = Path(sys.argv[2])
    if sys.argv[1] == 'check':
        check(site)
    elif '--count' in sys.argv:
        args = sys.argv
        c, r = int(args[args.index('--count') + 1]), args[args.index('--rating') + 1] if '--rating' in args else '5.0'
        print('stamped %d files, %d places' % stamp(site, c, r))
    else:
        d = read_data(site)
        print('stamped %d files, %d places with %s from %d' % (stamp(site, d['count'], d['rating']) + (d['rating'], d['count'])))
