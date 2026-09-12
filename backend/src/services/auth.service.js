const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const USERS_FILE = path.join(__dirname, '../data/users.json');

// Ensure data directory exists
const dataDir = path.dirname(USERS_FILE);
if (!fs.existsSync(dataDir)) {
  fs.mkdirSync(dataDir, { recursive: true });
}

// Initialize users file if it doesn't exist
if (!fs.existsSync(USERS_FILE)) {
  fs.writeFileSync(USERS_FILE, JSON.stringify([], null, 2));
}

class AuthService {
  getUsers() {
    try {
      const data = fs.readFileSync(USERS_FILE, 'utf8');
      return JSON.parse(data);
    } catch {
      return [];
    }
  }

  saveUsers(users) {
    fs.writeFileSync(USERS_FILE, JSON.stringify(users, null, 2));
  }

  hashPassword(password) {
    return crypto.createHash('sha256').update(password).digest('hex');
  }

  generateToken() {
    return crypto.randomBytes(32).toString('hex');
  }

  findUserByEmail(email) {
    const users = this.getUsers();
    return users.find(user => user.email.toLowerCase() === email.toLowerCase());
  }

  findUserByToken(token) {
    const users = this.getUsers();
    return users.find(user => user.token === token);
  }

  async register(email, password, name) {
    const users = this.getUsers();

    // Check if user already exists
    if (this.findUserByEmail(email)) {
      return { success: false, message: 'Email already registered' };
    }

    // Validate inputs
    if (!email || !password || !name) {
      return { success: false, message: 'All fields are required' };
    }

    if (password.length < 6) {
      return { success: false, message: 'Password must be at least 6 characters' };
    }

    // Create new user
    const newUser = {
      id: crypto.randomUUID(),
      email: email.toLowerCase(),
      password: this.hashPassword(password),
      name: name.trim(),
      token: null,
      createdAt: new Date().toISOString()
    };

    users.push(newUser);
    await this.saveUsers(users);

    return { 
      success: true, 
      message: 'Registration successful',
      user: { id: newUser.id, email: newUser.email, name: newUser.name }
    };
  }

  async login(email, password) {
    const users = this.getUsers();
    const user = this.findUserByEmail(email);

    if (!user) {
      return { success: false, message: 'Invalid email or password' };
    }

    if (user.password !== this.hashPassword(password)) {
      return { success: false, message: 'Invalid email or password' };
    }

    // Generate new token
    const token = this.generateToken();
    user.token = token;
    await this.saveUsers(users);

    return {
      success: true,
      message: 'Login successful',
      token: token,
      user: { id: user.id, email: user.email, name: user.name }
    };
  }

  logout(token) {
    const users = this.getUsers();
    const user = this.findUserByToken(token);

    if (user) {
      user.token = null;
      this.saveUsers(users);
    }

    return { success: true, message: 'Logged out successfully' };
  }

  validateToken(token) {
    if (!token) {
      return { valid: false, user: null };
    }

    const user = this.findUserByToken(token);
    if (!user) {
      return { valid: false, user: null };
    }

    return { 
      valid: true, 
      user: { id: user.id, email: user.email, name: user.name }
    };
  }
}

module.exports = new AuthService();
