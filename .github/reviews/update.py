#!/usr/bin/env python3
"""Keeps "5.0 from 37 Google reviews" on the live site in step with her Google Business Profile (Vegas, 9 Nov 2026:
"find out how we can automatically update the google review count on the site when new reviews come in", then "set that up", then
"this will work automatically in about a week without me doing anything?").

The live site's repo (github.com/vegasryan/Premier-Gutters-and-Exterior) carries this file at .github/reviews/update.py, the count at
.github/reviews/reviews.json, and the daily job at .github/workflows/google-reviews.yml. deploy/netlify-home/ship.py copies this file
there on every push and keeps the repo's reviews.json, so the repo's count always wins over the number typed into content/pages.json.

    python3 update.py check <dir>     read the count from Google; if it changed, write reviews.json and stamp every page in <dir>.
                                      The daily GitHub job runs this.
    python3 update.py stamp <dir>     stamp the pages in <dir> with <dir>/.github/reviews/reviews.json (ship.py runs this on its clone)
    python3 update.py stamp <dir> --count 38 --rating 5.0     the same with given numbers (a test; reviews.json is left alone)

What gets stamped: every "<b>5.0</b> from 37 Google reviews" (and <strong>, and the plain "5.0 from 37 Google reviews" in meta descriptions,
JSON-LD and llms.txt) in the site's .html, .txt, .xml and .json files. Nothing else on the page names the count. It stops if it finds none.

Google's side: Business Profile API v4 accounts.locations.reviews.list answers totalReviewCount and averageRating. It needs Google to
allowlist the Cloud project premier-gutters-reviews (number 967874129116; case 5-0271000041528, sent 9 Nov 2026) and an OAuth login from a
manager of her profile (elvegasryan@gmail.com). Until Google allowlists it, every call answers quota 0 and this waits quietly. On the first
run after approval it finishes the setup by itself:
  - finds her listing (Account Management and Business Information APIs) unless GBP_LOCATION is set;
  - turns on the v4 API ("Google My Business API", which Google won't turn on before approval) with the GCP_SA_KEY service account
    (api-switch@premier-gutters-reviews, Service Usage Admin on that project only), then reads the count.
If it's still waiting after WAIT_UNTIL, or anything else goes wrong, the job fails, and GitHub emails Vegas.

Secrets: GBP_CLIENT_ID, GBP_CLIENT_SECRET, GBP_REFRESH_TOKEN (connect.py login), GCP_SA_KEY (the service account's JSON key), and
optionally GBP_LOCATION ("accounts/<id>/locations/<id>"). Python standard library plus the openssl command, so the job needs no installs.
"""
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
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
WAIT_UNTIL = '2026-12-15'   # Google quoted 7 to 10 business days from 9 Nov; still waiting after this, the job fails so Vegas hears of it
BUSINESS = 'Premier Gutters'   # her listing's name starts with this
V4 = 'mybusiness.googleapis.com'


class GoogleError(Exception):
    def __init__(self, code, status, reason, message, url):
        super().__init__(f'Google said {code} {status} {reason} for {url}: {message}')
        self.code, self.status, self.reason, self.message = code, status, reason, message


class Waiting(Exception):
    """Google hasn't allowlisted the project yet (or the v4 API can't be turned on yet): not an error, try again tomorrow."""


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


# ---- talking to Google

def call(url, token=None, method='GET', body=None, form=None):
    data, headers = None, {}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
    elif body is not None:
        data, headers['Content-Type'] = json.dumps(body).encode(), 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors='replace')
        try:
            err = json.loads(raw)
        except ValueError:
            err = {'error': raw[:300]}
        err = err.get('error', err)
        if isinstance(err, str):   # the token endpoint answers {"error": "invalid_grant", "error_description": ...}
            raise GoogleError(e.code, err, '', raw[:300], url.split('?')[0]) from None
        reason = ' '.join(d.get('reason', '') for d in err.get('details', []) if isinstance(d, dict)).strip()
        raise GoogleError(e.code, err.get('status', ''), reason, (err.get('message') or '')[:400], url.split('?')[0]) from None


def post_form(url, fields):
    return call(url, method='POST', form=fields)


def get_json(url, token):
    return call(url, token)


def access_token():
    """Her profile's manager login (elvegasryan@gmail.com), from the refresh token connect.py saved."""
    try:
        return post_form('https://oauth2.googleapis.com/token', {
            'client_id': os.environ['GBP_CLIENT_ID'], 'client_secret': os.environ['GBP_CLIENT_SECRET'],
            'refresh_token': os.environ['GBP_REFRESH_TOKEN'], 'grant_type': 'refresh_token'})['access_token']
    except GoogleError as e:
        sys.exit(f'the Google login no longer works ({e}). Run deploy/google-reviews/connect.py login again.')


def sa_token():
    """The api-switch service account's token, from its JSON key (a signed JWT; openssl does the signing)."""
    key = json.loads(os.environ['GCP_SA_KEY'])
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b'=')
    now = int(time.time())
    msg = b64(json.dumps({'alg': 'RS256', 'typ': 'JWT'}).encode()) + b'.' + b64(json.dumps({
        'iss': key['client_email'], 'scope': 'https://www.googleapis.com/auth/cloud-platform',
        'aud': 'https://oauth2.googleapis.com/token', 'iat': now, 'exp': now + 600}).encode())
    fd, pem = tempfile.mkstemp(suffix='.pem')   # created readable by this user only
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(key['private_key'])
        sig = subprocess.run(['openssl', 'dgst', '-sha256', '-sign', pem], input=msg, capture_output=True, check=True).stdout
    finally:
        os.unlink(pem)
    jwt = (msg + b'.' + b64(sig)).decode()
    return post_form('https://oauth2.googleapis.com/token',
                     {'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer', 'assertion': jwt})['access_token'], key['project_id']


def not_allowlisted(e):
    return e.code == 429 or e.status == 'RESOURCE_EXHAUSTED'


def v4_off(e):
    return e.code == 403 and ('SERVICE_DISABLED' in e.reason or 'has not been used' in e.message or 'is disabled' in e.message)


def find_location(token):
    """Her listing as v4 wants it: accounts/<id>/locations/<id>."""
    try:
        accounts = get_json('https://mybusinessaccountmanagement.googleapis.com/v1/accounts?pageSize=20', token).get('accounts', [])
        hits = []
        for a in accounts:
            page = ''
            while True:
                r = get_json(f'https://mybusinessbusinessinformation.googleapis.com/v1/{a["name"]}/locations?readMask=name,title&pageSize=100'
                             + (f'&pageToken={page}' if page else ''), token)
                hits += [f'{a["name"]}/{loc["name"]}' for loc in r.get('locations', [])
                         if loc.get('title', '').lower().startswith(BUSINESS.lower())]
                page = r.get('nextPageToken')
                if not page:
                    break
    except GoogleError as e:
        if not_allowlisted(e):
            raise Waiting('Google has not allowlisted the project yet (quota 0)') from None
        raise
    hits = sorted(set(hits))
    if len(hits) != 1:
        sys.exit(f'expected one listing named "{BUSINESS}...", found {len(hits)}: {hits}. Set the GBP_LOCATION secret by hand.')
    return hits[0]


def turn_on_v4():
    """Turns on the v4 API in the project with the service account. Google refuses before approval; that's a Waiting, not an error."""
    if not os.environ.get('GCP_SA_KEY'):
        raise Waiting(f'{V4} is off and there is no GCP_SA_KEY to turn it on; turn it on in the Cloud console')
    token, project = sa_token()
    try:
        call(f'https://serviceusage.googleapis.com/v1/projects/{project}/services/{V4}:enable', token, method='POST', body={})
    except GoogleError as e:
        if e.code in (403, 404) or e.status in ('PERMISSION_DENIED', 'NOT_FOUND', 'FAILED_PRECONDITION'):
            raise Waiting(f'Google won\'t turn on {V4} yet ({e.code} {e.status}): the project is not allowlisted for it') from None
        raise
    print(f'turned on {V4} in {project}')


def from_google():
    token = access_token()
    loc = os.environ.get('GBP_LOCATION', '').strip().strip('/') or find_location(token)
    url = f'https://mybusiness.googleapis.com/v4/{loc}/reviews?pageSize=1'
    for attempt in range(8):
        try:
            data = get_json(url, token)
            break
        except GoogleError as e:
            if not_allowlisted(e):
                raise Waiting('Google has not allowlisted the project yet (quota 0)') from None
            if not v4_off(e):
                raise
            if attempt == 0:
                turn_on_v4()
            elif attempt == 7:
                raise Waiting(f'{V4} was just turned on and isn\'t answering yet; tomorrow\'s run will read it') from None
            time.sleep(20)   # a newly turned-on API takes a minute or two to answer
    count, avg = data.get('totalReviewCount'), data.get('averageRating')
    if not isinstance(count, int) or count < 1 or avg is None or not 1 <= float(avg) <= 5:
        sys.exit(f'unexpected answer from Google: totalReviewCount={count!r} averageRating={avg!r}')
    return count, rating_text(avg)


# ---- the daily job

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


def keepalive(site, old, today, note):
    """One quiet commit after 50 quiet days, so GitHub keeps the daily job switched on."""
    if last_commit_age_days(site) > KEEPALIVE_DAYS:
        old['checked'] = today
        data_file(site).write_text(json.dumps(old, indent=2) + '\n', encoding='utf-8')
        output(commit='true', message=f'Google reviews: {note}, {today} (keeps the daily job on) [skip netlify]')
    else:
        output(commit='false')


def check(site):
    missing = [k for k in ('GBP_CLIENT_ID', 'GBP_CLIENT_SECRET', 'GBP_REFRESH_TOKEN') if not os.environ.get(k)]
    if missing:
        print(f'not connected yet (no {", ".join(missing)}); nothing to do. See deploy/google-reviews/README.md in the project.')
        output(commit='false')
        return
    old = read_data(site)
    today = time.strftime('%Y-%m-%d', time.gmtime())
    try:
        count, rating = from_google()
    except Waiting as w:
        if today > WAIT_UNTIL:
            sys.exit(f'still waiting on Google after {WAIT_UNTIL}: {w}. Check case 5-0271000041528 (elvegasryan@gmail.com\'s email).')
        print(f'waiting on Google: {w}. The site keeps {old["rating"]} from {old["count"]}.')
        keepalive(site, old, today, f'waiting on Google, still {old["rating"]} from {old["count"]}')
        return
    if count == old['count'] and rating == old['rating']:
        print(f'no change: {rating} from {count} Google reviews')
        keepalive(site, old, today, f'still {rating} from {count}')
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
