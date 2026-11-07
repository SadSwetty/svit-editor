// Svit Editor — сервер-посередник між програмою і Claude (Cloudflare Worker).
//
// Справжній ключ Anthropic живе ТІЛЬКИ тут, у секреті ANTHROPIC_API_KEY.
// Програма надсилає замість нього код доступу (svit-…), який видає автор.
// Код можна будь-коли відкликати, і він більше нічого не відкриє.
//
// Секрети (Cloudflare → Worker → Settings → Variables and Secrets, тип Secret):
//   ANTHROPIC_API_KEY  — твій ключ sk-ant-…
//   ACCESS_CODES       — JSON: {"svit-КОД": {"name": "Оля", "per_day": 300}, ...}
//                        per_day — необов'язковий ліміт запитів на добу (потрібен KV, див. нижче)
// Необов'язково: KV-простір із назвою прив'язки USAGE — тоді працюють добові ліміти.

const UPSTREAM = "https://api.anthropic.com";

// Пропускаємо лише те, чим користується Svit Editor. Все інше — 404.
const ALLOWED = new Set([
  "POST /v1/messages",
  "POST /v1/messages/count_tokens",
  "GET /v1/models",
]);

// Заголовки, які дозволено передати від програми до Anthropic.
const FORWARD_REQ = ["content-type", "anthropic-version", "anthropic-beta", "accept"];
// Заголовки відповіді, які повертаємо програмі (без службових заголовків Anthropic про організацію).
const FORWARD_RESP = ["content-type", "request-id", "retry-after", "x-should-retry"];

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const route = `${req.method} ${url.pathname}`;

    if (url.pathname === "/" && req.method === "GET") {
      return new Response("Svit Editor server: OK\n", { headers: { "content-type": "text/plain; charset=utf-8" } });
    }
    if (!ALLOWED.has(route)) {
      return apiError(404, "not_found_error", "Not found");
    }
    if (!env.ANTHROPIC_API_KEY || !env.ACCESS_CODES) {
      return apiError(500, "api_error", "Сервер Svit ще не налаштований (немає секретів).");
    }

    // ---- код доступу
    const code = (req.headers.get("x-api-key") || "").trim();
    const user = await findUser(code, env.ACCESS_CODES);
    if (!user) {
      return apiError(401, "authentication_error", "Код доступу Svit недійсний або відкликаний.");
    }

    // ---- добовий ліміт (якщо підключено KV)
    if (env.USAGE && user.per_day) {
      const day = new Date().toISOString().slice(0, 10);
      const k = `${user.id}:${day}`;
      const n = parseInt((await env.USAGE.get(k)) || "0", 10);
      if (n >= user.per_day) {
        return apiError(429, "rate_limit_error", "Денний ліміт запитів для цього коду вичерпано. Спробуй завтра.");
      }
      await env.USAGE.put(k, String(n + 1), { expirationTtl: 60 * 60 * 48 });
    }

    // ---- запит до Anthropic зі справжнім ключем
    const headers = new Headers();
    for (const h of FORWARD_REQ) {
      const v = req.headers.get(h);
      if (v) headers.set(h, v);
    }
    if (!headers.has("anthropic-version")) headers.set("anthropic-version", "2023-06-01");
    headers.set("x-api-key", env.ANTHROPIC_API_KEY);

    let upstream;
    try {
      upstream = await fetch(UPSTREAM + url.pathname + url.search, {
        method: req.method,
        headers,
        // тіло передаємо потоком, не розбираючи: кадри з відео бувають великі
        body: req.method === "GET" ? undefined : req.body,
      });
    } catch (e) {
      return apiError(502, "api_error", "Сервер Svit не зміг з'єднатися з Claude.");
    }

    const out = new Headers();
    for (const h of FORWARD_RESP) {
      const v = upstream.headers.get(h);
      if (v) out.set(h, v);
    }
    // відповідь (зокрема потокова) іде програмі як є
    return new Response(upstream.body, { status: upstream.status, headers: out });
  },
};

// Шукає код у списку. Порівнюємо SHA-256 відбитки за сталий час, щоб час відповіді
// нічого не підказував про правильні коди.
async function findUser(code, codesJson) {
  if (!code.startsWith("svit-") || code.length < 20 || code.length > 200) return null;
  let codes;
  try {
    codes = JSON.parse(codesJson);
  } catch (e) {
    return null;
  }
  const got = await sha256(code);
  let found = null;
  for (const [c, info] of Object.entries(codes)) {
    const want = await sha256(c);
    if (equal(got, want) && !found) {
      found = { id: (await hex(want)).slice(0, 16), ...(info || {}) };
    }
  }
  return found;
}

async function sha256(s) {
  return new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s)));
}

function equal(a, b) {
  if (a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a[i] ^ b[i];
  return d === 0;
}

async function hex(bytes) {
  return [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// Помилки у форматі Anthropic — тоді бібліотека anthropic у програмі розуміє їх як звичайні.
function apiError(status, type, message) {
  return new Response(JSON.stringify({ type: "error", error: { type, message } }), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}
