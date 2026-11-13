"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const source = fs.readFileSync(path.join(__dirname, "../../llm-security-control-plane/guided-control-center/block-lab.js"), "utf8");
const context = {};
vm.runInNewContext(source.slice(0, source.indexOf("const enabledLabs")) + "\n" +
  source.slice(source.indexOf("function blockCode("), source.indexOf("const P23_FUNCTION_START")), context);

test("P04-02 preview places allowlist blocks at module scope", () => {
  const read = context.blockCode("P06", "read_action");
  const allowlist = context.blockCode("P06", "allowlist");
  assert.match(read, /^READ_ACTION =/m);
  assert.match(allowlist, /^ALLOWED_ACTIONS =/m);
  assert.doesNotMatch(read + "\n" + allowlist, /^ +(?:READ_ACTION|ALLOWED_ACTIONS) =/m);
});
