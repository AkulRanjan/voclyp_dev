/* Shared helpers: API-key storage (browser-local only) and authenticated fetch. */
"use strict";

const VoclypAPI = {
  key() { return localStorage.getItem("voclyp_api_key") || ""; },
  setKey(k) { localStorage.setItem("voclyp_api_key", (k || "").trim()); },

  async request(path, options) {
    const opts = options || {};
    opts.headers = Object.assign({}, opts.headers, { "X-API-Key": VoclypAPI.key() });
    const resp = await fetch(path, opts);
    if (resp.status === 401) throw new Error("invalid API key — set it on the home page");
    if (resp.status === 429) throw new Error("rate limited — slow down");
    return resp;
  },

  async json(path, options) {
    const resp = await VoclypAPI.request(path, options);
    if (!resp.ok) {
      let detail = resp.statusText;
      try { detail = (await resp.json()).detail || detail; } catch (e) { /* keep statusText */ }
      const err = new Error(detail);
      err.status = resp.status;
      throw err;
    }
    return resp.json();
  },
};

function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleString();
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
