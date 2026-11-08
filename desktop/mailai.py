"""MailAI local launcher. Account secrets use Windows DPAPI, current user scope."""
from pathlib import Path
from email.utils import parseaddr
import argparse,ctypes,hashlib,json,logging,os,re,sqlite3,ssl,sys,time,subprocess,urllib.request,uuid
from logging.handlers import RotatingFileHandler
DATA=Path(os.environ['MAILAI_DATA']) if os.environ.get('MAILAI_DATA') else Path(os.environ.get('LOCALAPPDATA',Path.home()))/'MailAI'/'Data'
def decrypt_config(path):
 class Blob(ctypes.Structure):_fields_=[('size',ctypes.c_uint32),('data',ctypes.POINTER(ctypes.c_ubyte))]
 raw=path.read_bytes();buffer=ctypes.create_string_buffer(raw);source=Blob(len(raw),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));output=Blob()
 if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source),None,None,None,None,1,ctypes.byref(output)):raise RuntimeError('Cannot open settings for this Windows user.')
 try:return json.loads(ctypes.string_at(output.data,output.size).decode('utf-8-sig'))
 finally:ctypes.windll.kernel32.LocalFree(output.data)
def parse_request(msg,config,fresh_text,is_reply):
 sender=parseaddr(str(msg.get('From','')))[1].lower()
 if not re.fullmatch(r'[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+',sender):return None,False,''
 if config.get('activation_mode','code')=='sender':
  if sender!=str(config.get('allowed_sender','')).strip().lower():return None,False,''
  body=fresh_text(msg).strip()
  if not body:return None,False,''
  reset=body in ('/new','שיחה חדשה')
  return 'sender:'+hashlib.sha256(sender.encode()).hexdigest()[:24],reset,'' if reset else body
 code=str(config.get('trigger_code',''))
 if not re.fullmatch(r'[0-9]{4}',code):raise ValueError('Four-digit code required.')
 body=fresh_text(msg);subject='' if is_reply(msg) else str(msg.get('Subject',''))
 token=re.compile(r'(?<![0-9])(?:'+re.escape(code+'0')+'|'+re.escape(code)+r')(?![0-9])');found=token.findall(body+'\n'+subject)
 if not found:return None,False,''
 sender=parseaddr(str(msg.get('From','')))[1].lower()
 if not re.fullmatch(r'[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+',sender):return None,False,''
 key=code+':'+hashlib.sha256(sender.encode()).hexdigest()[:24]
 return key,code+'0' in found,token.sub('',body if body.strip() else subject).strip()
def api_request(config,suffix,body=None):
 request=urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/'+suffix,data=None if body is None else json.dumps(body).encode(),headers={'x-goog-api-key':config['api_key'],'Content-Type':'application/json'})
 with urllib.request.urlopen(request,timeout=90,context=ssl.create_default_context()) as response:return json.load(response)
def choose_model(config):
 models=api_request(config,'models?pageSize=1000').get('models',[])
 names=[m['name'] for m in models if 'generateContent' in m.get('supportedGenerationMethods',[]) and 'flash' in m.get('name','') and not any(x in m['name'] for x in ('image','tts','live','native-audio','robotics'))]
 stable=[n for n in names if re.fullmatch(r'models/gemini-[0-9.]+-flash',n)]
 if not names:raise RuntimeError('No supported Flash model is available for this API key.')
 return sorted(stable or names,reverse=True)[0]
class ApiGemini:
 def __init__(self,config,headless=True):self.config=config;self.page=None;self.model=None
 def start(self):self.model=choose_model(self.config);self.page=object()
 def ask(self,prompt,chat_url='',on_chat=None):
  if self.page is None:self.start()
  key=chat_url if re.fullmatch(r'api:[a-f0-9]{32}',chat_url or '') else 'api:'+uuid.uuid4().hex
  with sqlite3.connect(DATA/'api-memory.sqlite3') as db:
   db.execute('CREATE TABLE IF NOT EXISTS chats(id TEXT PRIMARY KEY,history TEXT)');row=db.execute('SELECT history FROM chats WHERE id=?',(key,)).fetchone();history=(json.loads(row[0]) if row else [])[-22:]
   while len(json.dumps(history,ensure_ascii=False))>60000 and history:history=history[2:]
   contents=history+[{'role':'user','parts':[{'text':prompt}]}]
   result=api_request(self.config,self.model+':generateContent',{'systemInstruction':{'parts':[{'text':'Answer the email request helpfully. Use Hebrew when the user writes in Hebrew.'}]},'contents':contents,'generationConfig':{'maxOutputTokens':4096}})
   candidates=result.get('candidates',[]);text='\n'.join(p.get('text','') for p in (candidates[0].get('content',{}).get('parts',[]) if candidates else [])).strip()
   if not text:raise RuntimeError('No text answer returned.')
   history=contents+[{'role':'model','parts':[{'text':text}]}];db.execute('INSERT OR REPLACE INTO chats VALUES (?,?)',(key,json.dumps(history,ensure_ascii=False)))
  if on_chat:on_chat(key)
  return text
 def close(self):self.page=None
def setup_engine(config):
 import bot
 from thread_guard import fresh_text,is_reply
 bot.ROOT=DATA;bot.config=lambda require_code=True:config;bot.request_from=lambda msg,c:parse_request(msg,c,fresh_text,is_reply)
 if config.get('backend','browser')=='api':bot.Gemini=lambda headless=True:ApiGemini(config,headless);bot.verify_browser=lambda browser:browser.start()
 return bot

def wait_for_browser_login(engine):
 from playwright.sync_api import sync_playwright
 profile=DATA/'browser_profile';profile.mkdir(parents=True,exist_ok=True)
 portfile=profile/'DevToolsActivePort'
 portfile.unlink(missing_ok=True)
 child=subprocess.Popen([str(engine.find_chrome()),'--user-data-dir='+str(profile),'--remote-debugging-port=0','--remote-debugging-address=127.0.0.1','--no-first-run','https://gemini.google.com/app'])
 deadline=time.monotonic()+600;browser=None
 with sync_playwright() as pw:
  while time.monotonic()<deadline:
   if browser is None and portfile.exists():
    try:
     port=int(portfile.read_text().splitlines()[0])
     if not 1<=port<=65535:raise ValueError()
     browser=pw.chromium.connect_over_cdp('http://127.0.0.1:'+str(port),timeout=3000)
    except Exception:browser=None
   if browser is not None:
    if not browser.is_connected():raise RuntimeError('Login window was closed before sign-in completed.')
    for context in browser.contexts:
     for page in context.pages:
      if page.url.startswith('https://gemini.google.com/'):
       try:ready=page.locator("rich-textarea [contenteditable='true'], div.ql-editor[contenteditable='true']").first.is_visible()
       except Exception:ready=False
       if ready and any(c.get('name') in ('SID','__Secure-1PSID','__Secure-3PSID') and c.get('value') for c in context.cookies('https://gemini.google.com')):
        browser.close()
        print('AI_OK')
        return
   time.sleep(2)
 raise TimeoutError('Complete the Gemini sign-in and try connecting again.')

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--check-mail',action='store_true');parser.add_argument('--check-ai',action='store_true');parser.add_argument('--run',action='store_true');parser.add_argument('--wait-login',action='store_true');args=parser.parse_args();DATA.mkdir(parents=True,exist_ok=True)
 if sys.stdout and hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8',errors='replace')
 try:
  config=decrypt_config(DATA/'settings.dat');config.update(poll_seconds=15,headless=True);engine=setup_engine(config)
  engine.LOG.setLevel(logging.INFO);handler=RotatingFileHandler(DATA/'bot.log',maxBytes=1000000,backupCount=2,encoding='utf-8');handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'));engine.LOG.addHandler(handler)
  if args.check_mail:
   import smtplib
   with engine.connect_mail(config):pass
   with smtplib.SMTP_SSL('smtp.gmail.com',465,timeout=30,context=ssl.create_default_context()) as smtp:smtp.login(config['address'],config['app_password'])
   print('MAIL_OK')
  elif args.wait_login:
   with engine.SingleInstance():wait_for_browser_login(engine)
  elif args.check_ai:
   with engine.SingleInstance():
    browser=engine.Gemini(headless=True)
    try:engine.verify_browser(browser)
    finally:browser.close()
   print('AI_OK')
  elif args.run:
   with engine.SingleInstance():engine.run(config)
 except Exception as exc:
  if sys.stdout:print('ERROR:'+type(exc).__name__)
  return 1
 return 0
if __name__=='__main__':raise SystemExit(main())
