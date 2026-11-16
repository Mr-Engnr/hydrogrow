#!/usr/bin/env node
/**
 * dev_broker.js: LAPTOP-ONLY stand-in for Mosquitto.
 *
 * The Pi runs real Mosquitto (broker/mosquitto.conf). This is a tiny Aedes
 * broker so the ingest / backend / dashboard / fake_pi chain can be tested on
 * a Windows or Mac laptop without installing anything system-wide.
 *
 * Env (defaults match the Pi):
 *   MQTT_PORT      1883   plain MQTT listener
 *   MQTT_WS_PORT   9001   MQTT-over-WebSocket listener
 *   MQTT_BIND_HOST 0.0.0.0  interface to bind (MQTT_HOST is the *client-side*
 *                         address; a broker must bind, not connect, so it is
 *                         a separate knob)
 *
 *   cd tools && npm install && node dev_broker.js
 *   MQTT_PORT=1884 MQTT_WS_PORT=9002 node dev_broker.js   # when 1883 is taken
 */
const aedes = require("aedes")();
const net = require("net");
const http = require("http");
const ws = require("websocket-stream");

const MQTT_PORT = parseInt(process.env.MQTT_PORT || "1883", 10);
const WS_PORT = parseInt(process.env.MQTT_WS_PORT || "9001", 10);
const BIND_HOST = process.env.MQTT_BIND_HOST || "0.0.0.0";

function onListenError(name, port) {
  return (err) => {
    if (err.code === "EADDRINUSE") {
      console.error(`[dev_broker] ${name} port ${port} is already in use on ${BIND_HOST}.`);
      console.error(`[dev_broker] Something else (another broker, Docker, ThingsBoard...) owns it.`);
      console.error(`[dev_broker] Pick a free port, e.g. MQTT_PORT=1884 MQTT_WS_PORT=9002, and set the`);
      console.error(`[dev_broker] same MQTT_PORT for ingest.py, fake_pi.py, replay.py and the backend.`);
    } else {
      console.error(`[dev_broker] ${name} listen failed: ${err.message}`);
    }
    process.exit(1);
  };
}

const tcpServer = net.createServer(aedes.handle);
tcpServer.on("error", onListenError("MQTT", MQTT_PORT));
tcpServer.listen(MQTT_PORT, BIND_HOST, () =>
  console.log(`[dev_broker] mqtt://${BIND_HOST}:${MQTT_PORT}`));

const httpServer = http.createServer();
httpServer.on("error", onListenError("WebSocket", WS_PORT));
ws.createServer({ server: httpServer }, aedes.handle);
httpServer.listen(WS_PORT, BIND_HOST, () =>
  console.log(`[dev_broker] ws://${BIND_HOST}:${WS_PORT}`));

aedes.on("client", (c) => console.log(`[dev_broker] + ${c.id}`));
aedes.on("clientDisconnect", (c) => console.log(`[dev_broker] - ${c.id}`));
aedes.on("publish", (p, c) => {
  if (c) console.log(`[dev_broker] ${c.id} -> ${p.topic} qos${p.qos} ${p.payload.length}B`);
});

process.on("SIGINT", () => { aedes.close(() => process.exit(0)); });
process.on("SIGTERM", () => { aedes.close(() => process.exit(0)); });
