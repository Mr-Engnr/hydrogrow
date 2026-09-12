const authService = require('../services/auth.service');

exports.register = async (req, res) => {
  const { email, password, name } = req.body;

  try {
    const result = await authService.register(email, password, name);
    
    if (!result.success) {
      return res.status(400).json(result);
    }

    res.status(201).json(result);
  } catch (error) {
    console.error('Registration error:', error);
    res.status(500).json({ success: false, message: 'Registration failed' });
  }
};

exports.login = async (req, res) => {
  const { email, password } = req.body;

  try {
    const result = await authService.login(email, password);
    
    if (!result.success) {
      return res.status(401).json(result);
    }

    res.json(result);
  } catch (error) {
    console.error('Login error:', error);
    res.status(500).json({ success: false, message: 'Login failed' });
  }
};

exports.logout = async (req, res) => {
  const token = req.headers.authorization?.replace('Bearer ', '');

  try {
    const result = authService.logout(token);
    res.json(result);
  } catch (error) {
    console.error('Logout error:', error);
    res.status(500).json({ success: false, message: 'Logout failed' });
  }
};

exports.me = async (req, res) => {
  // req.user is set by auth middleware
  res.json({ success: true, user: req.user });
};
