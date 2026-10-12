// Render 무료 서버는 15분간 요청이 없으면 잠든다. 10분마다 /api/health를 불러 깨워 둔다.
// (무료 750시간/월 안에서 서버 하나를 24시간 켜 둘 수 있음)
const TARGET = "https://changwon-ansimgil.onrender.com/api/health";

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(fetch(TARGET, { headers: { "User-Agent": "ansimgil-keepalive" } }));
  },
  async fetch() {
    const res = await fetch(TARGET);
    return new Response(`keepalive → ${res.status}`, { headers: { "content-type": "text/plain; charset=utf-8" } });
  },
};
