export type PackageConfig={activation_mode:"code"|"sender";trigger_code:string;address:string;allowed_sender:string};
const email=(s:string)=>s.length<=254&&/^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}$/.test(s);
export function normalizePackageConfig(input:unknown):PackageConfig{
 if(!input||typeof input!=="object")throw Error("Invalid setup");
 const x=input as Record<string,unknown>,mode=x.activation_mode;
 const address=typeof x.address==="string"?x.address.trim().toLowerCase():"",sender=typeof x.allowed_sender==="string"?x.allowed_sender.trim().toLowerCase():"",code=typeof x.trigger_code==="string"?x.trigger_code:"";
 if(mode!=="code"&&mode!=="sender")throw Error("Invalid activation mode");
 if(!email(address))throw Error("Invalid bot email");
 if(mode==="code"&&!/^[0-9]{4}$/.test(code))throw Error("Invalid code");
 if(mode==="sender"&&!email(sender))throw Error("Invalid sender");
 return {activation_mode:mode,trigger_code:mode==="code"?code:"2468",address,allowed_sender:mode==="sender"?sender:""};
}
