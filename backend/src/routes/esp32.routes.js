const express = require("express");
const router = express.Router();
const esp32Controller = require("../controllers/esp32.controller");

router.get("/esp32data", esp32Controller.getESP32Data);

module.exports = router;
