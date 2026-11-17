const fs = require("fs");
const path = require("path");
const Database = require("better-sqlite3");
const { DB_PATH, SCHEMA_PATH } = require("../config/env.config");

// One shared connection. better-sqlite3 is synchronous, which is exactly what
// a single-process Express app on a Pi wants: no pool, no async leaks.
let db;

function open(dbPath = DB_PATH) {
  if (db) return db;
  fs.mkdirSync(path.dirname(dbPath), { recursive: true });
  db = new Database(dbPath);
  db.pragma("journal_mode = WAL");
  db.pragma("synchronous = NORMAL");
  db.pragma("busy_timeout = 5000");
  // Same schema file ingest.py applies; idempotent.
  db.exec(fs.readFileSync(SCHEMA_PATH, "utf8"));
  return db;
}

function get() {
  return db || open();
}

/** Test helper: point the module at a different file before first use. */
function reset(dbPath) {
  if (db) db.close();
  db = undefined;
  return open(dbPath);
}

module.exports = { open, get, reset };
