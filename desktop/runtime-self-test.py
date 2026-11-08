"""Offline integration check run with the bundled isolated Windows Python."""
import os
from pathlib import Path
from email.message import EmailMessage
import ssl,sqlite3
from playwright.sync_api import sync_playwright
import mailai,bot,thread_guard,web_reader
expected=Path(os.environ['MAILAI_RUNTIME_APP']).resolve()
for module in (mailai,bot,thread_guard,web_reader):
 assert Path(module.__file__).resolve().parent==expected, module.__name__
cfg=mailai.decrypt_config(mailai.DATA/'settings.dat')
assert cfg['trigger_code']=='0101' and cfg['address']=='demo.bot@gmail.com'
assert cfg['startup'] is True and cfg['app_password']=='abcdefghijklmnop'
engine=mailai.setup_engine(cfg)
message=EmailMessage();message['From']='sender@example.com';message['To']=cfg['address'];message.set_content('offline runtime check 0101')
key,reset,prompt=engine.request_from(message,cfg)
assert key.startswith('0101:') and not reset and prompt=='offline runtime check'
message.set_content('without a trigger');assert engine.request_from(message,cfg)[0] is None
print('PORTABLE_RUNTIME_OK: own modules, Playwright, DPAPI settings and configured code routing')
