"""Require a fresh trigger in each reply; ignore quoted history and reply subject."""
import copy
import functools
import re
from html.parser import HTMLParser

class NewTextHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts=[];self.stack=[];self.cut=False
    def handle_starttag(self,tag,attrs):
        attrs={k:(v or '') for k,v in attrs}
        tokens=(attrs.get('class','')+' '+attrs.get('id','')).lower().split()
        quoted=tag=='blockquote' or any(x in tokens for x in ('gmail_quote','gmail_quote_container','gmail_attr','yahoo_quoted','moz-cite-prefix','protonmail_quote','divrplyfwdmsg','replyforwardmsg')) or attrs.get('type','').lower()=='cite'
        if any(x in tokens for x in ('divrplyfwdmsg','replyforwardmsg')):self.cut=True
        hidden=quoted or tag in ('script','style','head','template') or 'display:none' in attrs.get('style','').replace(' ','').lower() or attrs.get('aria-hidden','')=='true'
        skip=self.cut or hidden or (self.stack[-1][1] if self.stack else False)
        void=tag in ('area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr')
        if not skip and tag in ('br','p','div','li','tr'):self.parts.append('\n')
        if not void:self.stack.append((tag,skip))
    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        self.handle_endtag(tag)
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==tag:
                skip=self.stack[i][1];del self.stack[i:]
                if not skip and tag in ('p','div','li','tr'):self.parts.append('\n')
                break
    def handle_data(self,text):
        if not self.cut and not (self.stack and self.stack[-1][1]):self.parts.append(text)


def strip_history(text):
    text=text.replace('\r\n','\n').replace('\r','\n')
    lines=text.splitlines();out=[]
    for i,line in enumerate(lines):
        s=re.sub('[\u200e\u200f\u202a-\u202e\u2066-\u2069]','',line).strip()
        if s.startswith('>') or s=='--':break
        if re.match(r'^[-_]{2,}\s*(?:Original Message|Forwarded message|הודעה מקורית|הודעה שהועברה)',s,re.I):break
        if re.match(r'^(?:On\s+.+wrote\s*:|בתאריך\s+.+(?:כתב|כתבה|נכתב)|ב[יום]?[׳\x27]?\s*.+(?:כתב|כתבה)\s*:)',s,re.I):break
        # Gmail can wrap its attribution over several lines.
        joined=' '.join(x.strip() for x in lines[i:i+5])
        if (s.startswith('On ') and re.search(r'\bwrote\s*:',joined,re.I)) or (s.startswith('בתאריך ') and re.search(r'כתב|כתבה|נכתב',joined)):break
        if re.match(r'^(?:From|מאת|מ)\s*:',s,re.I):
            following='\n'.join(lines[i+1:i+7])
            if re.search(r'^(?:Sent|Date|To|Subject|נשלח|תאריך|אל|נושא)\s*:',following,re.I|re.M):break
        if re.match(r'^[-_]{5,}\s*$',s) and re.search(r'^(?:From|מאת)\s*:','\n'.join(lines[i+1:i+5]),re.I|re.M):break
        out.append(line)
    return '\n'.join(out).strip()[:20000]


def fresh_text(msg):
    html=msg.get_body(preferencelist=('html',))
    if html is not None and html.get_content_type()=='text/html':
        parser=NewTextHTML();parser.feed(html.get_content())
        return strip_history(''.join(parser.parts))
    plain=msg.get_body(preferencelist=('plain',))
    if plain is None or plain.get_content_type()!='text/plain':return ''
    return strip_history(plain.get_content())


def is_reply(msg):
    return bool(msg.get('In-Reply-To') or msg.get('References') or re.match(r'^\s*(?:re|fw|fwd|aw|sv|השב|תגובה|העבר)\s*:',str(msg.get('Subject','')),re.I))


def install_thread_guard(namespace):
    if namespace.get('_fresh_code_guard_installed'):return
    original=namespace['request_from']
    @functools.wraps(original)
    def request(msg,*args,**kwargs):
        clean=copy.copy(msg)
        clean.clear_content()
        clean.set_content(fresh_text(msg))
        if is_reply(msg):
            if 'Subject' in clean:del clean['Subject']
        return original(clean,*args,**kwargs)
    namespace['prompt_from']=fresh_text
    namespace['request_from']=request
    namespace['_fresh_code_guard_installed']=True
