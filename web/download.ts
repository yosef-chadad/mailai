import {configTrailer} from './exe-config';
import {normalizePackageConfig} from './package-config';
export type Manifest={version:string;bytes:number;sha256:string;parts:{name:string;bytes:number;sha256:string}[]};
const locationOf=(file:string)=>new URL('./downloads/'+file,document.baseURI).href;
export async function getManifest(){const r=await fetch(locationOf('manifest.json'),{cache:'no-store'});if(!r.ok)throw Error('Download not ready');const m=await r.json() as Manifest;if(!m.parts?.length||m.bytes>250_000_000)throw Error('Invalid package');return m}
const hex=(bytes:ArrayBuffer)=>Array.from(new Uint8Array(bytes),n=>n.toString(16).padStart(2,'0')).join('');
export async function downloadPersonalBot(input:unknown,progress:(n:number)=>void){
 const config=normalizePackageConfig(input),manifest=await getManifest(),buffers:ArrayBuffer[]=[];let total=0;
 for(const part of manifest.parts){if(!/^MailAI\.part[0-9]+$/.test(part.name))throw Error('Invalid package');const r=await fetch(locationOf(part.name)+'?sha='+part.sha256,{cache:'force-cache'});if(!r.ok)throw Error('Download failed');const bytes=await r.arrayBuffer();if(bytes.byteLength!==part.bytes||hex(await crypto.subtle.digest('SHA-256',bytes))!==part.sha256)throw Error('Integrity check failed');buffers.push(bytes);total+=bytes.byteLength;progress(Math.round(total/manifest.bytes*100))}
 if(total!==manifest.bytes)throw Error('Incomplete package');
 const core=new Blob(buffers);if(hex(await crypto.subtle.digest('SHA-256',await core.arrayBuffer()))!==manifest.sha256)throw Error('Integrity check failed');
 const data=configTrailer(config),blob=new Blob([core,data as BlobPart],{type:'application/vnd.microsoft.portable-executable'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=config.activation_mode==='sender'?'MailAI-Personal.exe':`MailAI-${config.trigger_code}.exe`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);
}
