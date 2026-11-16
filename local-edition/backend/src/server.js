const app = require("./app");
const db = require("./db/db");
const authService = require("./services/auth.service");
const { PORT, DB_PATH, DEMO_USER_EMAIL, DEMO_USER_PASSWORD, DEMO_USER_NAME } = require("./config/env.config");

async function main() {
  db.open();
  const seed = await authService.seedDemoUser(DEMO_USER_EMAIL, DEMO_USER_PASSWORD, DEMO_USER_NAME);
  console.log(`db ${DB_PATH} users=${authService.userCount()} demo-user: ${seed.seeded ? "seeded" : seed.reason}`);

  const server = app.listen(PORT, "0.0.0.0", () => {
    console.log(`HydroGrow backend listening on http://0.0.0.0:${PORT}`);
  });

  const stop = () => {
    console.log("shutting down");
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(0), 2000).unref();
  };
  process.on("SIGTERM", stop);
  process.on("SIGINT", stop);
}

main().catch((e) => {
  console.error("fatal:", e);
  process.exit(1);
});
