"""Compile WinForms ahead of time and package with standard NSIS. No script bootstrap."""
from pathlib import Path
import hashlib,json,os,subprocess,zlib
ROOT=Path(__file__).resolve().parent;BUILD=ROOT/'build';PUBLIC=ROOT.parent/'public/downloads';TOOLS=ROOT.parents[1]/'windows-build-tools'
def main():
 BUILD.mkdir(exist_ok=True);PUBLIC.mkdir(parents=True,exist_ok=True)
 dotnet=Path(os.environ.get('MAILAI_DOTNET',TOOLS/'dotnet/dotnet'));sdk=dotnet.parent
 csc=sorted(sdk.glob('sdk/*/Roslyn/bincore/csc.dll'))[-1]
 refs=Path(os.environ.get('MAILAI_NET48_REFS',TOOLS/'net48/build/.NETFramework/v4.8'))
 assemblies=['mscorlib','System','System.Core','System.Drawing','System.Windows.Forms','System.Security','System.Web.Extensions']
 command=[str(dotnet),str(csc),'-nologo','-noconfig','-nostdlib+','-target:winexe','-platform:x64','-optimize+','-debug-','-deterministic+','-out:'+str(BUILD/'MailAI.exe'),'-win32icon:'+str(ROOT/'icon.ico'),'-win32manifest:'+str(ROOT/'app.manifest')]
 command+=['-r:'+str(refs/(n+'.dll')) for n in assemblies]
 command += [str(ROOT/'MailAI.cs'),str(ROOT/'AssemblyInfo.cs')]
 subprocess.run(command,check=True,cwd=ROOT)
 nsis=Path(os.environ.get('MAILAI_NSIS',TOOLS/'nsis/usr/bin/makensis'))
 environment=dict(os.environ,NSISDIR=os.environ.get('MAILAI_NSISDIR',str(TOOLS/'nsis/usr/share/nsis')))
 subprocess.run([str(nsis),'-V2',str(ROOT/'installer.nsi')],check=True,cwd=ROOT,env=environment)
 blob=(BUILD/'MailAI-Setup.exe').read_bytes();parts=[];chunk_size=8*1024*1024
 for old in PUBLIC.glob('MailAI.part*'):old.unlink()
 for at in range(0,len(blob),chunk_size):
  content=blob[at:at+chunk_size];name='MailAI.part'+str(at//chunk_size+1);(PUBLIC/name).write_bytes(content);parts.append({'name':name,'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()})
 manifest={'version':'1.5.0','format':'connect-first-installer','name':'MailAI-Setup.exe','bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest(),'crc32':zlib.crc32(blob)&0xffffffff,'parts':parts}
 (PUBLIC/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest,indent=2))
if __name__=='__main__':main()
