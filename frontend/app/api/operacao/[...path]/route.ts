import { NextRequest, NextResponse } from "next/server";

// Homologação local: o endereço upstream é fixo, sem proxy arbitrário.
const upstream = "http://127.0.0.1:8000/v1";
const cookieName = "fg_homolog_session";
type Context = { params: Promise<{path: string[]}> };

function localOnly(req: NextRequest) {
  const host = req.headers.get("host");
  return /^(?:localhost|127\.0\.0\.1)(?::[0-9]{1,5})?$/.test(host ?? "");
}
function response(data: unknown, status = 200) {
  return NextResponse.json(data, {status, headers: {"Cache-Control":"no-store"}});
}
function sameOrigin(req: NextRequest) {
  return req.headers.get("origin") === `${req.nextUrl.protocol}//${req.headers.get("host")}`;
}
async function call(path: string, init: RequestInit) {
  return fetch(upstream + path, {...init, cache:"no-store", redirect:"error", signal:AbortSignal.timeout(8000)});
}
function clearCookie(res: NextResponse) {
  res.cookies.set(cookieName,"",{path:"/",httpOnly:true,sameSite:"strict",maxAge:0});
  return res;
}

export async function POST(req: NextRequest, ctx: Context) {
  if (!localOnly(req) || !sameOrigin(req)) return response({detail:"Acesso local obrigatório."},403);
  const {path}=await ctx.params;
  const route = path.join("/");
  if (route !== "session" && route !== "company-search") return response({detail:"Não permitido."},405);
  if (!(req.headers.get("content-type")||"").startsWith("application/json")) return response({detail:"JSON obrigatório."},415);
  try {
    const raw=await req.text();
    if(raw.length>4096) return response({detail:"Requisição inválida."},400);
    const input=JSON.parse(raw);
    if (route === "company-search") {
      const token = req.cookies.get(cookieName)?.value;
      if (!token) return response({detail:"Autenticação necessária."},401);
      const result = await call("/company-search", {
        method:"POST",
        headers:{"Content-Type":"application/json",Authorization:"Bearer "+token},
        body:JSON.stringify(input),
      });
      if (result.status === 401) return clearCookie(response({detail:"Sessão expirada."},401));
      return response(await result.json(),result.status);
    }
    if(typeof input?.login!=="string" || typeof input?.senha!=="string") return response({detail:"Credenciais inválidas."},400);
    const prior=req.cookies.get(cookieName)?.value;
    if(prior) await call("/session",{method:"DELETE",headers:{Authorization:"Bearer "+prior}});
    const result=await call("/session",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({login:input.login,senha:input.senha})});
    if(!result.ok) return clearCookie(response({detail:result.status===429?"Muitas tentativas.":"Não foi possível autenticar."},result.status));
    const session=await result.json();
    if(typeof session.access_token!=="string" || !session.usuario) return clearCookie(response({detail:"Sessão inválida."},502));
    const out=response({usuario:session.usuario});
    out.cookies.set(cookieName,session.access_token,{httpOnly:true,sameSite:"strict",secure:req.nextUrl.protocol==="https:",path:"/",maxAge:1800});
    return out;
  } catch {
    return clearCookie(response({detail:"API indisponível ou solicitação inválida."},502));
  }
}

export async function DELETE(req: NextRequest, ctx: Context) {
  if (!localOnly(req) || !sameOrigin(req)) return response({detail:"Acesso local obrigatório."},403);
  if ((await ctx.params).path.join("/") !== "session") return response({detail:"Não permitido."},405);
  const token=req.cookies.get(cookieName)?.value;
  try {
    if(token) {
      const result = await call("/session",{method:"DELETE",headers:{Authorization:"Bearer "+token}});
      if (!result.ok) throw new Error("Revogação indisponível");
    }
  } catch {
    return clearCookie(response({detail:"Sessão local encerrada; revogação remota não confirmada."},502));
  }
  return clearCookie(response({ok:true}));
}

export async function GET(req: NextRequest, ctx: Context) {
  if(!localOnly(req)) return response({detail:"Acesso local obrigatório."},403);
  const path=(await ctx.params).path.join("/");
  if(!/^(me|campaigns|leads(?:\/[1-9][0-9]*)?)$/.test(path)) return response({detail:"Rota inexistente."},404);
  const token=req.cookies.get(cookieName)?.value;
  if(!token) return response({detail:"Autenticação necessária."},401);
  const params=new URLSearchParams();
  for(const key of ["view","campaign_id","limit","offset"]) {
    const value=req.nextUrl.searchParams.get(key);
    if(value!==null) params.set(key,value);
  }
  try {
    const result=await call("/"+path+(params.size?"?"+params.toString():""),{headers:{Authorization:"Bearer "+token}});
    if(result.status===401) return clearCookie(response({detail:"Sessão expirada."},401));
    if(!result.ok) return response({detail:result.status===404?"Registro não encontrado.":result.status===403?"Acesso não autorizado.":"Consulta indisponível."},result.status);
    return response(await result.json());
  } catch {
    return response({detail:"API local indisponível."},502);
  }
}
