// Proxy same-origin para o agent-api.
//
// Por que um Route Handler e não `rewrites()` em next.config.ts: o destino de um rewrite
// é resolvido quando o Next.js CARREGA a config — no `output: "standalone"` isso acontece
// em `next build`, dentro do estágio de build da imagem, onde AGENT_API_URL não está
// definida (só o docker-compose define essa env var no serviço `web`, em RUNTIME). O
// destino ficava congelado em "http://localhost:8080" e a env var do compose não tinha
// nenhum efeito depois de construída a imagem.
//
// Um Route Handler roda o corpo da função a cada requisição, no processo Node.js do
// container em runtime — lê `process.env.AGENT_API_URL` de verdade, sem rebuild. O
// contrato para o browser não muda: continua tudo same-origin em /api/*, zero URL ou
// chave de API no bundle do cliente.

import { NextRequest, NextResponse } from "next/server";

const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "transfer-encoding",
  "content-encoding",
  "content-length",
  "host",
]);

function agentApiUrl(): string {
  return process.env.AGENT_API_URL ?? "http://localhost:8080";
}

async function proxy(req: NextRequest, path: string[]): Promise<NextResponse> {
  const target = `${agentApiUrl()}/${path.join("/")}${req.nextUrl.search}`;

  const headers = new Headers();
  req.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) headers.set(key, value);
  });

  const hasBody = !["GET", "HEAD"].includes(req.method);

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: req.method,
      headers,
      body: hasBody ? await req.arrayBuffer() : undefined,
      // @ts-expect-error -- duplex é exigido pelo undici ao enviar body em streaming; não faz parte do tipo do DOM fetch ainda.
      duplex: hasBody ? "half" : undefined,
      cache: "no-store",
    });
  } catch {
    return NextResponse.json(
      { error: "upstream_unreachable", message: "agent-api indisponível", conversation_id: null },
      { status: 502 },
    );
  }

  const outHeaders = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) outHeaders.set(key, value);
  });

  return new NextResponse(upstream.body, { status: upstream.status, headers: outHeaders });
}

interface RouteContext {
  params: Promise<{ path: string[] }>;
}

export async function GET(req: NextRequest, ctx: RouteContext) {
  return proxy(req, (await ctx.params).path);
}

export async function POST(req: NextRequest, ctx: RouteContext) {
  return proxy(req, (await ctx.params).path);
}

export async function PUT(req: NextRequest, ctx: RouteContext) {
  return proxy(req, (await ctx.params).path);
}

export async function DELETE(req: NextRequest, ctx: RouteContext) {
  return proxy(req, (await ctx.params).path);
}
