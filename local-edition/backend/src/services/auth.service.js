const crypto = require("crypto");
const bcrypt = require("bcryptjs");
const db = require("../db/db");

const SALT_ROUNDS = 10;

/**
 * Same mechanism as the original file-backed service (the
 * existing token flow is unchanged): opaque random bearer tokens stored on the user row,
 * one active token per user, rotated on login, cleared on logout.
 * Storage moved from src/data/users.json to the users table in SQLite.
 * bcryptjs produces/verifies the same $2b$ hashes as the native bcrypt module,
 * so users.json records can be imported unchanged (see importUsersJson).
 */
class AuthService {
  hashPassword(password) {
    return bcrypt.hash(password, SALT_ROUNDS);
  }

  verifyPassword(password, hash) {
    return bcrypt.compare(password, hash);
  }

  generateToken() {
    return crypto.randomBytes(32).toString("hex");
  }

  findUserByEmail(email) {
    return db.get().prepare("SELECT * FROM users WHERE email = ?").get(String(email || "").toLowerCase());
  }

  findUserByToken(token) {
    if (!token) return undefined;
    return db.get().prepare("SELECT * FROM users WHERE token = ?").get(token);
  }

  publicUser(user) {
    return { id: user.id, email: user.email, name: user.name };
  }

  async register(email, password, name) {
    if (this.findUserByEmail(email)) {
      return { success: false, message: "Email already registered" };
    }
    if (!email || !password || !name) {
      return { success: false, message: "All fields are required" };
    }
    if (password.length < 6) {
      return { success: false, message: "Password must be at least 6 characters" };
    }
    const newUser = {
      id: crypto.randomUUID(),
      email: email.toLowerCase(),
      password: await this.hashPassword(password),
      name: name.trim(),
      token: null,
      createdAt: new Date().toISOString(),
    };
    db.get().prepare(
      "INSERT INTO users (id, email, password, name, token, created_at) VALUES (@id, @email, @password, @name, @token, @createdAt)"
    ).run(newUser);
    return { success: true, message: "Registration successful", user: this.publicUser(newUser) };
  }

  async login(email, password) {
    const user = this.findUserByEmail(email);
    if (!user) {
      return { success: false, message: "Invalid email or password" };
    }
    if (!(await this.verifyPassword(password, user.password))) {
      return { success: false, message: "Invalid email or password" };
    }
    const token = this.generateToken();
    db.get().prepare("UPDATE users SET token = ? WHERE id = ?").run(token, user.id);
    return { success: true, message: "Login successful", token, user: this.publicUser(user) };
  }

  logout(token) {
    const user = this.findUserByToken(token);
    if (user) {
      db.get().prepare("UPDATE users SET token = NULL WHERE id = ?").run(user.id);
    }
    return { success: true, message: "Logged out successfully" };
  }

  validateToken(token) {
    if (!token) return { valid: false, user: null };
    const user = this.findUserByToken(token);
    if (!user) return { valid: false, user: null };
    return { valid: true, user: this.publicUser(user) };
  }

  /** Create the .env demo user once; no-op if the email already exists. */
  async seedDemoUser(email, password, name) {
    if (!email || !password) return { seeded: false, reason: "DEMO_USER_EMAIL / DEMO_USER_PASSWORD not set" };
    if (this.findUserByEmail(email)) return { seeded: false, reason: "exists" };
    const r = await this.register(email, password, name || "Expo Demo");
    return { seeded: r.success, reason: r.message };
  }

  /** Import records from the old users.json (array of {id,email,password,name,token,createdAt}). */
  importUsersJson(records) {
    const stmt = db.get().prepare(
      "INSERT OR IGNORE INTO users (id, email, password, name, token, created_at) VALUES (?,?,?,?,?,?)"
    );
    let n = 0;
    for (const u of records || []) {
      n += stmt.run(u.id, String(u.email).toLowerCase(), u.password, u.name, null, u.createdAt || new Date().toISOString()).changes;
    }
    return n;
  }

  userCount() {
    return db.get().prepare("SELECT COUNT(*) AS n FROM users").get().n;
  }
}

module.exports = new AuthService();
