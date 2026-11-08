"""Personal Gmail -> Gemini website -> Gmail bridge. No Gemini API key."""
from pathlib import Path
from email import policy
from email.parser import BytesParser
from email.message import EmailMessage
from email.utils import parseaddr, make_msgid, formatdate
from html.parser import HTMLParser
import argparse
import getpass
import html
import imaplib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import re
import smtplib
import sqlite3
import ssl
import sys
import time

_bootstrap = argparse.ArgumentParser(add_help=False)
_bootstrap.add_argument('--data-dir', type=Path)
_bootstrap_args, _ = _bootstrap.parse_known_args()
ROOT = (_bootstrap_args.data_dir or Path(__file__).resolve().parent).resolve()
CONFIG = ROOT / 'config.json'
LOG = logging.getLogger('bot')
def validate_code(code):
    if not isinstance(code, str) or not re.fullmatch(r'[0-9]{1,20}', code):
        raise ValueError('Choose a numeric code (1-20 digits) in 2_CHOOSE_CODE.bat.')
    return code


def read_code():
    path = ROOT / 'code_settings.json'
    if not path.exists():
        raise RuntimeError('Run 2_CHOOSE_CODE.bat first.')
    return validate_code(json.loads(path.read_text(encoding='utf-8'))['trigger_code'])


def choose_code():
    if not (ROOT / 'accounts.ready').exists():raise RuntimeError('Run 1_CONNECT_ACCOUNTS.bat first.')
    print('בחירת הקוד האישי להפעלת הבוט')
    print('כשמוסיפים 0 לקוד הזה, מתחילים שיחה חדשה ונקייה.')
    print('Choose your numeric code. Adding 0 at the END starts a new chat.')
    code = validate_code(input('Your code / הקוד שלך: ').strip())
    path = ROOT / 'code_settings.json'
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps({'trigger_code': code}), encoding='utf-8')
    tmp.replace(path)
    c=config(require_code=False)
    c['trigger_code']=code
    save_config(c)
    (ROOT / 'setup.ready').write_text(str(time.time()),encoding='ascii')
    print(f'קוד לשאלה ולהמשך שיחה: {code}')
    print(f'כשמוסיפים 0 לקוד הזה, זו שיחה חדשה: {code}0')
    print(f'Continue: {code} | New chat: {code}0')
    print('Step 2 complete. Next: 3_INSTALL_AND_START.bat')


def save_config(c):
    tmp = CONFIG.with_suffix('.tmp')
    tmp.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(CONFIG)


def setup():
    code = read_code() if (ROOT / 'code_settings.json').exists() else None
    print('Gemini Email Bot - Gmail setup (Windows 64-bit)')
    print('No Gemini API key. Use a Gmail APP PASSWORD, not your normal password.')
    print('Create one at https://myaccount.google.com/apppasswords (2-step verification required).')
    address = input('Bot Gmail address: ').strip().lower()
    password = getpass.getpass('16-character Gmail app password (hidden): ').replace(' ', '')
    if not valid_address(address) or not password:
        raise ValueError('Invalid bot Gmail address or missing app password.')
    if code:print(f'Your code: {code} | New chat: {code}0')
    print('Messages from any address are accepted when they contain a conversation code.')
    c = dict(address=address, app_password=password, trigger_code=code,
             poll_seconds=15, headless=True)
    print('Checking IMAP and SMTP login; no messages will be sent...')
    with connect_mail(c):
        pass
    with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=30, context=ssl.create_default_context()) as s:
        s.login(address, password)
    save_config(c)
    print('Saved. Password is stored locally in config.json; keep the folder private.')
    print('Email configured. Next: sign in to Gemini.')


def valid_address(s):
    return bool(re.fullmatch(r'[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+', s))


def config(require_code=True):
    if not CONFIG.exists():
        raise RuntimeError('Run 1_CONNECT_ACCOUNTS.bat first.')
    c = json.loads(CONFIG.read_text(encoding='utf-8'))
    if not valid_address(c.get('address', '')) or not c.get('app_password'):
        raise ValueError('Missing bot Gmail address or app password. Run 1_CONNECT_ACCOUNTS.bat.')
    if require_code:validate_code(c.get('trigger_code'))
    # Legacy allowed_senders is intentionally ignored in the all-senders edition.
    return c


def connect_mail(c):
    m = imaplib.IMAP4_SSL('imap.gmail.com', timeout=30)
    try:
        m.login(c['address'], c['app_password'])
        status, _ = m.select('INBOX', readonly=True)
        if status != 'OK':
            raise RuntimeError('Cannot open INBOX.')
        return m
    except BaseException:
        try:
            m.logout()
        except Exception:
            pass
        raise


class TextHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        if tag in ('br', 'p', 'div', 'li'):
            self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.hidden:
            self.hidden -= 1
        if tag in ('p', 'div', 'li'):
            self.parts.append('\n')
    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def prompt_from(msg):
    part = msg.get_body(preferencelist=('plain', 'html'))
    if part is None:
        return ''
    text = part.get_content()
    if part.get_content_type() == 'text/html':
        parser = TextHTML()
        parser.feed(text)
        text = ''.join(parser.parts)
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if re.match(r'^On .+wrote:\s*$', s) or re.match(r'^בתאריך .+כתב.*:', s) or s == '--':
            break
        if not s.startswith('>'):
            lines.append(line)
    return '\n'.join(lines).strip()[:20000]


def eligible(msg, c):
    sender = parseaddr(str(msg.get('From', '')))[1].lower()
    if not valid_address(sender):
        return False
    if msg.get('X-Gemini-Bot-Reply') or msg.get('Auto-Submitted', 'no').lower() != 'no':
        return False
    if msg.get('List-Id') or msg.get_content_type() == 'multipart/report':
        return False
    if msg.get('Precedence', '').lower() in ('bulk', 'list', 'junk'):
        return False
    return bool(request_from(msg, c)[0])


def request_from(msg, c):
    """A single chosen code identifies this installation's active conversation.
    Match its reset form first; quoted history/attachments do not trigger it.
    """
    code = validate_code(c.get('trigger_code'))
    reset_code = code + '0'
    pattern = re.compile(re.escape(reset_code) + '|' + re.escape(code))
    subject = str(msg.get('Subject', ''))
    body = prompt_from(msg)
    commands = pattern.findall(subject + '\n' + body)
    if not commands:
        return None, False, ''
    reset = reset_code in commands
    prompt = pattern.sub('', body if body.strip() else subject).strip()
    if not body.strip():
        prompt = re.sub(r'^(?:Re:\s*)+', '', prompt, flags=re.IGNORECASE).strip()
    return code, reset, prompt


def meta_get(db, key):
    row = db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
    return row[0] if row else ''


def meta_set(db, key, value):
    db.execute('INSERT OR REPLACE INTO meta(key,value) VALUES (?,?)', (key, value))


def prepare_memory(db, code, reset, request_token):
    # The same reset request is not repeated if a later SMTP/login attempt fails.
    with db:
        if reset and meta_get(db, 'last_reset_request:' + code) != request_token:
            meta_set(db, 'active_chat_url:' + code, '')
            meta_set(db, 'last_reset_request:' + code, request_token)
    return meta_get(db, 'active_chat_url:' + code)


def reply_message(msg, c, answer, reply_id, images=None):
    reply = EmailMessage()
    reply['From'] = c['address']
    reply['To'] = parseaddr(str(msg['From']))[1]
    subject = str(msg.get('Subject', 'Gemini'))
    reply['Subject'] = subject if subject.lower().startswith('re:') else 'Re: ' + subject
    reply['Date'] = formatdate(localtime=True)
    reply['Message-ID'] = reply_id
    reply['Auto-Submitted'] = 'auto-replied'
    reply['X-Gemini-Bot-Reply'] = 'true'
    if msg.get('Message-ID'):
        reply['In-Reply-To'] = str(msg['Message-ID'])
        reply['References'] = (str(msg.get('References', '')) + ' ' + str(msg['Message-ID'])).strip()[-8000:]
    reply.set_content(str(answer) + '\n\n---\nתשובה אוטומטית מ-Gemini')
    reply.add_alternative('<div dir="auto" style="font-family:Arial;white-space:pre-wrap">' + html.escape(str(answer)) + '</div>', subtype='html')
    validated = []
    for item in images or []:
        add_image(validated, item['data'])
    for item in validated:
        reply.add_attachment(item['data'], maintype='image', subtype=item['subtype'], filename=item['filename'])
    return reply


class Gemini:
    def __init__(self, headless=True):
        self.headless = headless
        self.pw = self.ctx = self.page = None
    def start(self):
        from playwright.sync_api import sync_playwright
        self.pw = sync_playwright().start()
        self.ctx = self.pw.chromium.launch_persistent_context(
            str(ROOT / 'browser_profile'), executable_path=str(find_chrome()), headless=self.headless, accept_downloads=True,
            viewport={'width': 1440, 'height': 1000})
        self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
        self.page.goto('https://gemini.google.com/app', timeout=60000)
    def ask(self, prompt, chat_url="", on_chat=None):
        if not self.page or self.page.is_closed():
            self.close()
            self.start()
        if chat_url and not re.fullmatch(r'https://gemini\.google\.com/app/[A-Za-z0-9_-]+', chat_url):
            raise RuntimeError('Invalid saved Gemini conversation URL.')
        self.page.goto(chat_url or 'https://gemini.google.com/app', timeout=60000)
        editor = self.page.locator("rich-textarea [contenteditable='true'], div.ql-editor[contenteditable='true']").first
        editor.wait_for(state='visible', timeout=45000)
        responses = self.page.locator('model-response')
        before = responses.count()
        if not chat_url and before:
            raise RuntimeError('Gemini did not open a clean chat.')
        if chat_url:
            self.page.wait_for_url(chat_url, timeout=15000)
            responses.first.wait_for(state='attached', timeout=30000)
            before = responses.count()
        editor.fill(prompt)
        send = self.page.locator("button[aria-label='Send message'], button[aria-label*='שלח'], button.send-button").first
        if send.count() and send.is_visible():
            send.click()
        else:
            editor.press('Enter')
        deadline = time.monotonic() + 360
        previous = None
        saved_url = ''
        stable_since = time.monotonic()
        while time.monotonic() < deadline:
            if (ROOT / 'STOP').exists():
                raise InterruptedError('Stopped by user.')
            self.page.wait_for_timeout(1000)
            current_url = self.page.url.split('?')[0].rstrip('/')
            if current_url != saved_url and re.fullmatch(r'https://gemini\.google\.com/app/[A-Za-z0-9_-]+', current_url):
                if on_chat:
                    on_chat(current_url)
                saved_url = current_url
            if responses.count() <= before:
                continue
            response = responses.last
            markdown = response.locator('.markdown, .markdown-main-panel')
            text = markdown.first.inner_text().strip() if markdown.count() else response.inner_text().strip()
            candidates = response_images(response)
            signature = (text, image_signature(candidates))
            if signature != previous:
                previous, stable_since = signature, time.monotonic()
            stop = self.page.locator("button[aria-label*='Stop'], button[aria-label*='עצור']")
            busy = any(x.is_visible() for x in stop.all())
            copy = response.locator("button[aria-label='Copy'], button[aria-label='העתקה'], [data-test-id='copy-button']")
            downloads = response.locator("button[aria-label*='Download'], button[aria-label*='הורד'], button[aria-label*='הורדה']")
            # Image-only responses may have a download control without a text-copy button.
            completed = bool(copy.count() or (candidates and downloads.count()))
            placeholder = response.locator('generated-image, image-generation-response, .generated-image').count()
            waiting_image = bool(placeholder and not candidates)
            if (text or candidates) and not busy and completed and not waiting_image and time.monotonic() - stable_since >= 8:
                if not saved_url:
                    raise RuntimeError('Gemini chat URL was not saved; cannot preserve conversation memory.')
                images = collect_response_images(self, response, candidates) if candidates else []
                if candidates and not images:
                    text += '\n\nנוצרה תמונה באתר, אך לא ניתן היה לצרף אותה למייל. נסה שוב.'
                return GeneratedAnswer(text or 'התמונה שנוצרה מצורפת למייל.', images)
        raise TimeoutError('No completed Gemini text response. Check login, quota, and website layout.')
    def close(self):
        try:
            if self.ctx:
                self.ctx.close()
        finally:
            if self.pw:
                self.pw.stop()
            self.pw = self.ctx = self.page = None


def db_open(path):
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)')
    db.execute('''CREATE TABLE IF NOT EXISTS jobs (
        validity TEXT, uid INTEGER, status TEXT NOT NULL DEFAULT 'pending',
        attempts INTEGER NOT NULL DEFAULT 0, answer TEXT, reply_id TEXT,
        PRIMARY KEY(validity, uid))''')
    if 'attachments' not in {row[1] for row in db.execute('PRAGMA table_info(jobs)')}:
        db.execute('ALTER TABLE jobs ADD COLUMN attachments TEXT')
    db.execute("UPDATE jobs SET status='uncertain' WHERE status='sending'")
    # Migrate the former single conversation to 2010 once, without reviving it
    # after a reset. Other codes always start independently.
    for old in ('active_chat_url', 'last_reset_request'):
        db.execute('INSERT OR IGNORE INTO meta(key,value) SELECT ?,value FROM meta WHERE key=?',
                   (old + ':2010', old))
    db.commit()
    return db


def uids(mail, criteria):
    status, data = mail.uid('search', None, criteria)
    if status != 'OK':
        raise RuntimeError('IMAP search failed')
    return [int(x) for x in (data[0] or b'').split()]


def queue_new(db, mail):
    validity_data = mail.response('UIDVALIDITY')[1]
    if not validity_data or not validity_data[0]:
        raise RuntimeError('No IMAP UIDVALIDITY; refusing to guess.')
    validity = validity_data[0].decode('ascii')
    key = 'cursor:' + validity
    row = db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
    if row is None:
        # First run only: baseline must succeed before any cursor is recorded.
        existing = uids(mail, 'ALL')
        cursor = max(existing, default=0)
        db.execute('INSERT INTO meta VALUES (?,?)', (key, str(cursor)))
        db.commit()
        LOG.info('Baseline recorded. Only messages arriving after this point will be processed.')
        return validity
    cursor = int(row[0])
    new = sorted(x for x in uids(mail, f'UID {cursor+1}:*') if x > cursor)
    with db:
        for uid in new:
            db.execute('INSERT OR IGNORE INTO jobs(validity,uid) VALUES (?,?)', (validity, uid))
        if new:
            db.execute('UPDATE meta SET value=? WHERE key=?', (str(new[-1]), key))
    return validity


def process(db, mail, browser, c, validity, uid, attempts, answer, reply_id):
    key = (validity, uid)
    status, data = mail.uid('fetch', str(uid), '(BODY.PEEK[])')
    chunks = [x[1] for x in (data or []) if isinstance(x, tuple)]
    if status != 'OK' or not chunks:
        raise RuntimeError('Cannot fetch queued message; it may have moved out of INBOX.')
    if len(chunks[0]) > 2_000_000:
        db.execute("UPDATE jobs SET status='skipped' WHERE validity=? AND uid=?", key)
        db.commit()
        return
    msg = BytesParser(policy=policy.default).parsebytes(chunks[0])
    allowed = eligible(msg, c)
    # Both distributed editions retain their own parser and conversation settings.
    code, reset, prompt = request_from(msg, c) if len(inspect.signature(request_from).parameters) == 2 else request_from(msg)
    if not allowed or (not prompt and not reset):
        db.execute("UPDATE jobs SET status='skipped' WHERE validity=? AND uid=?", key)
        db.commit()
        return
    row = db.execute('SELECT attachments FROM jobs WHERE validity=? AND uid=?', key).fetchone()
    images = unpack_images(row[0]) if row and row[0] else []
    if answer is None:
        chat_url = prepare_memory(db, code, reset, f'{validity}:{uid}')
        if not prompt and reset:
            answer = 'התחלנו שיחה חדשה. שלח שאלה עם הקוד האישי שלך כדי להמשיך.'
        else:
            if browser.page is None:
                browser.start()
            def remember(url):
                with db:
                    meta_set(db, 'active_chat_url:' + code, url)
            result = browser.ask(prompt, chat_url=chat_url, on_chat=remember)
            answer, images = str(result), getattr(result, 'images', [])
        reply_id = make_msgid(domain=c['address'].split('@')[-1])
        db.execute('UPDATE jobs SET answer=?,reply_id=?,attachments=? WHERE validity=? AND uid=?',
                   (answer, reply_id, pack_images(images), *key))
        db.commit()
    reply = reply_message(msg, c, answer, reply_id, images=images)
    with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=40, context=ssl.create_default_context()) as smtp:
        smtp.login(c['address'], c['app_password'])
        db.execute("UPDATE jobs SET status='sending' WHERE validity=? AND uid=?", key)
        db.commit()
        try:
            smtp.send_message(reply)
        except Exception:
            db.execute("UPDATE jobs SET status='uncertain' WHERE validity=? AND uid=?", key)
            db.commit()
            LOG.error('UID %s: delivery uncertain; check Gmail Sent before retrying.', uid)
            return
        db.execute("UPDATE jobs SET status='done', answer=NULL, attachments=NULL WHERE validity=? AND uid=?", key)
        db.commit()
        LOG.info('UID %s replied successfully, with %s image attachment(s).', uid, len(images))


class SingleInstance:
    def __enter__(self):
        self.file = open(ROOT / 'bot.lock', 'a+b')
        self.file.seek(0)
        self.file.write(b'0')
        self.file.flush()
        self.file.seek(0)
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                self.file.close()
                raise RuntimeError('Bot or Gemini login is already running. Stop it first.')
        else:
            import fcntl
            fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        (ROOT / 'STOP').unlink(missing_ok=True)
        return self
    def __exit__(self, *args):
        self.file.close()


def run(c):
    db = db_open(ROOT / 'state.sqlite3')
    browser = Gemini(c.get('headless', True))
    LOG.info('Bot starting. Checking saved Gemini sign-in in background.')
    try:
        verify_browser(browser)
        LOG.info('Gemini ready. Polling INBOX.')
        while not (ROOT / 'STOP').exists():
            try:
                with connect_mail(c) as mail:
                    validity = queue_new(db, mail)
                    write_status()
                    pending = db.execute("SELECT uid,attempts,answer,reply_id FROM jobs WHERE validity=? AND status='pending' ORDER BY uid LIMIT 10", (validity,)).fetchall()
                    for uid, attempts, answer, reply_id in pending:
                        if (ROOT / 'STOP').exists():
                            break
                        try:
                            process(db, mail, browser, c, validity, uid, attempts, answer, reply_id)
                        except Exception as exc:
                            # Avoid logging mail contents or server errors containing account data.
                            state = db.execute('SELECT status FROM jobs WHERE validity=? AND uid=?', (validity, uid)).fetchone()[0]
                            if state == 'pending':
                                db.execute("UPDATE jobs SET attempts=attempts+1,status=? WHERE validity=? AND uid=?", ('failed' if attempts+1 >= 3 else 'pending', validity, uid))
                                db.commit()
                            LOG.error('UID %s failed (%s). See TROUBLESHOOTING in README.', uid, type(exc).__name__)
                            try:
                                browser.close()
                            except Exception:
                                pass
                            # Keep conversational requests in order while retrying.
                            break
            except Exception as exc:
                LOG.error('Mail connection/check failed (%s); retrying.', type(exc).__name__)
            for _ in range(max(5, int(c.get('poll_seconds', 15)))):
                if (ROOT / 'STOP').exists():
                    break
                time.sleep(1)
    finally:
        browser.close()
        db.close()
        LOG.info('Bot stopped.')


def find_chrome():
    locations = [Path(os.environ.get(k, '')) / 'Google/Chrome/Application/chrome.exe'
                 for k in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA')]
    chrome = next((p for p in locations if p.is_file()), None)
    if chrome is None:
        raise RuntimeError('Install Google Chrome for Windows first.')
    return chrome


def login_gemini():
    import subprocess
    subprocess.Popen([str(find_chrome()), '--user-data-dir=' + str(ROOT / 'browser_profile'),
                      '--no-first-run', 'https://gemini.google.com/app'])
    input('Sign in to YOUR Gemini account. CLOSE that Chrome window completely, then press Enter here...')


def verify_browser(browser):
    browser.start()
    browser.page.locator("rich-textarea [contenteditable='true'], div.ql-editor[contenteditable='true']").first.wait_for(state='visible', timeout=45000)


def initialize_inbox(c):
    db = db_open(ROOT / 'state.sqlite3')
    try:
        with connect_mail(c) as mail:
            queue_new(db, mail)
    finally:
        db.close()


def configure_all():
    (ROOT / 'accounts.ready').unlink(missing_ok=True)
    (ROOT / 'setup.ready').unlink(missing_ok=True)
    setup()
    login_gemini()
    print('Checking saved Gemini sign-in in a hidden browser. No question will be sent...')
    browser = Gemini(headless=True)
    try:
        verify_browser(browser)
    finally:
        browser.close()
    initialize_inbox(config(require_code=False))
    (ROOT / 'accounts.ready').write_text(str(time.time()), encoding='ascii')
    print('Step 1 complete. Run 2_CHOOSE_CODE.bat next.')


def write_status():
    status = ROOT / 'status.json'
    tmp = status.with_suffix('.tmp')
    tmp.write_text(json.dumps({'last_mail_check': time.time(), 'pid': os.getpid()}), encoding='utf-8')
    tmp.replace(status)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--choose-code', action='store_true')
    parser.add_argument('--configure', action='store_true')
    parser.add_argument('--background', action='store_true')
    parser.add_argument('--setup', action='store_true')
    parser.add_argument('--login', action='store_true')
    parser.add_argument('--retry-failed', action='store_true')
    args = parser.parse_args()
    ROOT.mkdir(parents=True, exist_ok=True)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    LOG.setLevel(logging.INFO)
    fh = RotatingFileHandler(ROOT / 'bot.log', maxBytes=1_000_000, backupCount=3, encoding='utf-8')
    fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    LOG.addHandler(fh)
    if sys.stdout:
        LOG.addHandler(logging.StreamHandler(sys.stdout))
    try:
        with SingleInstance():
            if args.choose_code:
                choose_code()
            elif args.configure:
                configure_all()
            elif args.setup:
                setup()
            elif args.login:
                login_gemini()
            elif args.retry_failed:
                db = db_open(ROOT / 'state.sqlite3')
                db.execute("UPDATE jobs SET status='pending',attempts=0 WHERE status='failed'")
                db.commit()
                db.close()
                print('Failed jobs requeued. Uncertain deliveries were NOT requeued.')
            else:
                c = config()
                if args.background:
                    c['headless'] = True
                run(c)
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        LOG.error('Startup failed (%s).', type(exc).__name__)
        if sys.stdout:
            print(str(exc))
        return 1
    return 0


import base64

import hashlib

import inspect

import tempfile

from urllib.parse import urlsplit

IMAGE_UPDATE_VERSION = 1

MAX_IMAGE_BYTES = 8 * 1024 * 1024

MAX_TOTAL_IMAGE_BYTES = 12 * 1024 * 1024

MAX_IMAGES = 4

class GeneratedAnswer(str):
    def __new__(cls, text, images=None):
        obj = super().__new__(cls, text)
        obj.images = images or []
        return obj

def image_type(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    if data.startswith(b'\xff\xd8\xff'):
        return 'jpeg'
    if data.startswith((b'GIF87a', b'GIF89a')):
        return 'gif'
    if len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'webp'
    if len(data) >= 16 and data[4:8] == b'ftyp' and data[8:12] in (b'avif', b'avis'):
        return 'avif'
    return None

def add_image(images, data):
    subtype = image_type(data)
    if not subtype or not data or len(data) > MAX_IMAGE_BYTES or len(images) >= MAX_IMAGES:
        return False
    if sum(len(x['data']) for x in images) + len(data) > MAX_TOTAL_IMAGE_BYTES:
        return False
    digest = hashlib.sha256(data).hexdigest()
    if any(hashlib.sha256(x['data']).hexdigest() == digest for x in images):
        return False
    ext = 'jpg' if subtype == 'jpeg' else subtype
    images.append({'data': data, 'subtype': subtype, 'filename': f'gemini_image_{len(images)+1}.{ext}'})
    return True

def pack_images(images):
    valid = []
    for item in images or []:
        add_image(valid, item['data'])
    return json.dumps([{'data': base64.b64encode(x['data']).decode('ascii'),
                        'subtype': x['subtype'], 'filename': x['filename']} for x in valid])

def unpack_images(value):
    images = []
    if value:
        for item in json.loads(value):
            add_image(images, base64.b64decode(item['data'], validate=True))
    return images

def response_images(response):
    result = []
    for img in response.locator('img').all():
        try:
            info = img.evaluate('(el) => ({src:el.currentSrc||el.src, complete:el.complete, width:el.naturalWidth, height:el.naturalHeight})')
            box = img.bounding_box()
            # Ignore avatars, icons, citations and unloaded image placeholders.
            if (info['complete'] and max(info['width'], info['height']) >= 256 and min(info['width'], info['height']) >= 64
                    and box and max(box['width'], box['height']) >= 120 and min(box['width'], box['height']) >= 64):
                result.append((img, info['src']))
        except Exception:
            continue
    return result[:MAX_IMAGES]

def image_signature(images):
    return tuple(src for _, src in images)

def image_bytes_from_source(context, img, src):
    if src.startswith('data:image/'):
        header, data = src.split(',', 1)
        if ';base64' in header and len(data) <= MAX_IMAGE_BYTES * 4 // 3 + 8:
            return base64.b64decode(data, validate=True)
    if src.startswith('blob:'):
        value = img.evaluate('''async (el) => {
            const url = el.currentSrc || el.src;
            if (!url.startsWith('blob:')) return null;
            const blob = await (await fetch(url)).blob();
            if (blob.size > 8388608) return null;
            return await new Promise((resolve, reject) => {
                const reader = new FileReader(); reader.onload = () => resolve(reader.result);
                reader.onerror = reject; reader.readAsDataURL(blob);
            });
        }''')
        if value:
            return image_bytes_from_source(context, img, value)
    parsed = urlsplit(src)
    host = (parsed.hostname or '').lower()
    # Only fetch Google-hosted output, with the authenticated browser cookie jar.
    if parsed.scheme == 'https' and (host == 'googleusercontent.com' or host.endswith('.googleusercontent.com')
                                    or host == 'ggpht.com' or host.endswith('.ggpht.com')):
        response = context.request.get(src, timeout=20000, max_redirects=0)
        try:
            if response.ok and int(response.headers.get('content-length', '0')) <= MAX_IMAGE_BYTES:
                data = response.body()
                if len(data) <= MAX_IMAGE_BYTES:
                    return data
        finally:
            response.dispose()
    return b''

def collect_response_images(browser, response, candidates):
    images = []
    # Prefer Gemini's own download control so the original file is attached.
    for img, _ in candidates:
        try:
            img.hover(timeout=1500)
        except Exception:
            pass
    buttons = response.locator("button[aria-label*='Download'], button[aria-label*='download'], button[aria-label*='הורד'], button[aria-label*='הורדה'], button[data-test-id*='download']")
    for index, (img, src) in enumerate(candidates):
        success = False
        if index < buttons.count():
            try:
                with tempfile.TemporaryDirectory(prefix='gemini-image-', dir=ROOT) as directory:
                    with browser.page.expect_download(timeout=20000) as download_info:
                        buttons.nth(index).click(timeout=4000)
                    download = download_info.value
                    path = Path(directory) / 'image.bin'
                    download.save_as(str(path))
                    if path.stat().st_size <= MAX_IMAGE_BYTES:
                        success = add_image(images, path.read_bytes())
            except Exception:
                pass
        if not success:
            try:
                success = add_image(images, image_bytes_from_source(browser.ctx, img, src))
            except Exception:
                pass
        if not success:
            # A PNG capture of this one output image is a last-resort preview.
            try:
                success = add_image(images, img.screenshot(type='png', timeout=5000))
            except Exception:
                pass
        if not success:
            LOG.warning('An output image could not be attached (unavailable or size limit).')
    return images


WEB_READER_UPDATE_VERSION = 1
from web_reader import install_web_reader as _install_web_reader
_install_web_reader(Gemini)


FRESH_REPLY_CODE_UPDATE_VERSION = 1
from thread_guard import install_thread_guard as _install_thread_guard
_install_thread_guard(globals())

if __name__ == '__main__':
    raise SystemExit(main())
