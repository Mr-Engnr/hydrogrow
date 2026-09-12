const authService = require('../services/auth.service');

const authMiddleware = (req, res, next) => {
  const token = req.headers.authorization?.replace('Bearer ', '');

  if (!token) {
    return res.status(401).json({ 
      success: false, 
      message: 'Authentication required' 
    });
  }

  const result = authService.validateToken(token);

  if (!result.valid) {
    return res.status(401).json({ 
      success: false, 
      message: 'Invalid or expired token' 
    });
  }

  req.user = result.user;
  next();
};

module.exports = authMiddleware;
