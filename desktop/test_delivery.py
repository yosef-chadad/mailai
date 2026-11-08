"""Exercise the real queued-message pipeline with offline mail/AI adapters."""
import tempfile,unittest
from pathlib import Path
from email.message import EmailMessage
from unittest.mock import patch
import mailai
class DeliveryTests(unittest.TestCase):
 def test_delivery_and_dedup(self):
  cfg={'address':'bot@gmail.com','app_password':'abcdefghijklmnop','activation_mode':'code','trigger_code':'0101'}
  engine=mailai.setup_engine(cfg)
  class Inbox:
   def __init__(self):self.raw=b''
   def uid(self,*args):return 'OK',[(b'message',self.raw)]
  class AI:
   page=object()
   def ask(self,prompt,chat_url='',on_chat=None):return 'offline answer: '+prompt
  class SMTP:
   sent=[]
   def __init__(self,*a,**kw):pass
   def __enter__(self):return self
   def __exit__(self,*a):pass
   def login(self,*a):pass
   def send_message(self,m):self.sent.append(m)
  with tempfile.TemporaryDirectory() as folder,patch.object(engine,'ROOT',Path(folder)),patch.object(engine.smtplib,'SMTP_SSL',SMTP):
   db=engine.db_open(Path(folder)/'state.sqlite3');inbox=Inbox()
   for uid,text,reply in [(1,'hello 0101',False),(2,'no trigger',False),(3,'reply without trigger',True)]:
    msg=EmailMessage();msg['From']='sender@example.com';msg['To']=cfg['address'];msg['Subject']='Re: 0101' if reply else 'test';msg['Message-ID']=f'<{uid}@example.com>'
    if reply:msg['In-Reply-To']='<previous@example.com>'
    msg.set_content(text);inbox.raw=msg.as_bytes();db.execute('INSERT INTO jobs(validity,uid) VALUES (?,?)',('1',uid));db.commit();engine.process(db,inbox,AI(),cfg,'1',uid,0,None,None)
   states=db.execute('SELECT status FROM jobs ORDER BY uid').fetchall();self.assertEqual([r[0] for r in states],['done','skipped','skipped']);self.assertEqual(len(SMTP.sent),1);self.assertIn('offline answer:',SMTP.sent[0].get_body(preferencelist=('plain',)).get_content());db.close()
if __name__=='__main__':unittest.main()
