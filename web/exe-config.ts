import type {PackageConfig} from './package-config';
/** Data-only overlay supported by NSIS; never patches executable instructions or CRC. */
export function configTrailer(config:PackageConfig){
 const body=new TextEncoder().encode(JSON.stringify(config));
 if(body.length>4096)throw Error('Setup too large');
 const result=new Uint8Array(body.length+12);result.set(body);
 new DataView(result.buffer).setUint32(body.length,body.length,true);
 result.set(new TextEncoder().encode('MAILAI13'),body.length+4);return result;
}
