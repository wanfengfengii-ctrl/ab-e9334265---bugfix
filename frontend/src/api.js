/** 调用后端对位 API */

function extractDetail(data) {
  if (!data) return null;
  const d = data.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    const msgs = d
      .map((item) => (item && item.msg ? String(item.msg).replace(/^Value error,\s*/, "") : ""))
      .filter(Boolean);
    if (msgs.length) return msgs.join("；");
  }
  return null;
}

export async function postMatch(payload) {
  let res;
  try {
    res = await fetch("/api/match", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (e) {
    throw new Error(`无法连接后端服务：${e.message}`);
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    throw new Error(extractDetail(data) || `请求失败（HTTP ${res.status}）`);
  }
  return data;
}
