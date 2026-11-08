import unittest
from email.message import EmailMessage
from thread_guard import fresh_text,is_reply
from mailai import parse_request
class Tests(unittest.TestCase):
 def message(self,text,sender='one@example.com',subject='Hello',reply=False):
  m=EmailMessage();m['From']=sender;m['Subject']=subject
  if reply:m['In-Reply-To']='<previous@example.com>'
  m.set_content(text);return m
 def parse(self,m):return parse_request(m,{'trigger_code':'0101'},fresh_text,is_reply)
 def test_zero(self):
  key,reset,prompt=self.parse(self.message('שלום 0101'));self.assertTrue(key.startswith('0101:'));self.assertFalse(reset);self.assertEqual(prompt,'שלום')
 def test_no_substrings(self):
  for text in ('10101','70101','010101','010107'):self.assertIsNone(self.parse(self.message(text))[0])
 def test_reset(self):self.assertTrue(self.parse(self.message('חדש 01010'))[1])
 def test_quoted_history(self):self.assertIsNone(self.parse(self.message('בלי קוד\nOn Friday User wrote:\n> 0101',subject='Re: 0101',reply=True))[0])
 def test_html_quote(self):
  m=self.message('בלי קוד',reply=True);m.add_alternative('<div>בלי קוד</div><blockquote>0101</blockquote>',subtype='html');self.assertIsNone(self.parse(m)[0])
 def test_sender_memory(self):
  a=self.parse(self.message('0101','one@example.com'))[0];b=self.parse(self.message('0101','two@example.com'))[0];self.assertNotEqual(a,b);self.assertEqual(a,self.parse(self.message('01010','one@example.com'))[0])
 def test_initial_subject(self):self.assertIsNotNone(self.parse(self.message('שאלה',subject='0101'))[0])
 def personal(self,m):return parse_request(m,{'activation_mode':'sender','allowed_sender':'one@example.com'},fresh_text,is_reply)
 def test_personal_no_code(self):
  key,reset,prompt=self.personal(self.message('שלום ללא קוד','User <ONE@example.com>'));self.assertTrue(key.startswith('sender:'));self.assertFalse(reset);self.assertEqual(prompt,'שלום ללא קוד')
 def test_personal_other_sender(self):self.assertIsNone(self.personal(self.message('שלום 0101','two@example.com'))[0])
 def test_personal_quoted_only(self):self.assertIsNone(self.personal(self.message('On Friday User wrote:\n> שאלה קודמת',reply=True))[0])
 def test_personal_reset(self):
  key,reset,prompt=self.personal(self.message('/new'));self.assertTrue(reset);self.assertEqual(prompt,'');self.assertEqual(key,self.personal(self.message('שאלה חדשה'))[0])
if __name__=='__main__':unittest.main()
