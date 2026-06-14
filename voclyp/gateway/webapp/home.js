/* Landing page: save the API key and confirm it authenticates. */
"use strict";

const keyInput = document.getElementById("api-key");
const status = document.getElementById("key-status");
keyInput.value = VoclypAPI.key();

async function checkKey() {
  if (!VoclypAPI.key()) { status.textContent = "no key set yet"; return; }
  try {
    await VoclypAPI.json("/v1/insights");
    status.textContent = "✓ key works — pick a view below";
    status.className = "status-line ok";
  } catch (e) {
    status.textContent = "✗ " + e.message;
    status.className = "status-line err";
  }
}

document.getElementById("save-key").addEventListener("click", () => {
  VoclypAPI.setKey(keyInput.value);
  checkKey();
});
checkKey();
