from pathlib import Path
import hashlib,json,struct,zlib
root=Path(__file__).resolve().parent
blob=(root/'build/MailAI-Setup.exe').read_bytes()
first=blob.find(b'\xef\xbe\xad\xdeNullsoftInst')-4
assert first>=0
end=first+struct.unpack_from('<I',blob,first+24)[0]
assert end==len(blob)
assert zlib.crc32(blob[512:end-4])&0xffffffff==struct.unpack_from('<I',blob,end-4)[0]
folder=root.parent/'public/downloads';folder.mkdir(parents=True,exist_ok=True)
parts=[]
for i,offset in enumerate(range(0,len(blob),8*1024*1024),1):
 body=blob[offset:offset+8*1024*1024];name=f'MailAI.part{i}';(folder/name).write_bytes(body);parts.append({'name':name,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()})
manifest={'version':'1.5.2','format':'connect-first-installer','name':'MailAI-Setup.exe','bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest(),'crc32':zlib.crc32(blob)&0xffffffff,'parts':parts}
(folder/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest,indent=2))
