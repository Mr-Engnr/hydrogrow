// The dashboard is served by this same Express process (same origin), Unity is
// not a browser, and the whole system lives on an isolated LAN. Any origin is
// therefore accepted; the old Azure App Service origins are gone.
const corsOptions = {
  origin: true,
  methods: ["GET", "POST"],
  allowedHeaders: ["Content-Type", "Authorization"],
};

module.exports = corsOptions;
