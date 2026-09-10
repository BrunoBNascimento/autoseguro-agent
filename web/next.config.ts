import type { NextConfig } from "next";

// O browser fala só com o próprio Next em /api/*; quem repassa para o agent-api é o
// Route Handler em app/api/[...path]/route.ts, não um rewrite daqui.
//
// Um rewrite() seria resolvido quando esta config é CARREGADA (em `next build`, dentro
// do estágio de build da imagem), onde AGENT_API_URL ainda não existe — só o
// docker-compose define essa env var em runtime, no serviço `web`. O destino ficaria
// congelado em localhost e a env var do compose nunca teria efeito depois de construída
// a imagem. O Route Handler lê a env var a cada requisição, em runtime de verdade.
const nextConfig: NextConfig = {
  output: "standalone",
};

export default nextConfig;
