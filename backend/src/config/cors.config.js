const allowedOrigins = [
  "http://localhost:3000",
  "http://localhost:3003",
  "https://hydrogrow-backend.azurewebsites.net",
  "http://hydrogrow-backend.azurewebsites.net"
];

const corsOptions = {
  origin: function (origin, callback) {
    // Allow requests with no origin (like mobile apps or curl)
    if (!origin) return callback(null, true);
    
    if (allowedOrigins.includes(origin)) {
      callback(null, true);
    } else {
      callback(new Error("Not allowed by CORS"));
    }
  },
  methods: ["GET", "POST"],
  allowedHeaders: ["Content-Type", "Authorization"]
};

module.exports = corsOptions;
