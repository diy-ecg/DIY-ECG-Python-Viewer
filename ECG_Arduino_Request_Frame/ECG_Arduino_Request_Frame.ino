#include <TimerOne.h>

// Request/response binary framing with continuous sampling.
// Host sends 'R' to request a frame. The Arduino sends all samples collected
// since the last request from a ring buffer.
// Frame layout (little-endian):
// [uint8 count][count * uint16 sample][count * uint32 t_ms][uint16 crc16]

// 5 ms -> 200 Hz. Needs 16-bit to avoid overflow when passing 5000 microseconds.
const uint16_t SAMPLE_INTERVAL_US = 5000;
const uint16_t RING_SIZE         = 200;     // max samples kept between requests = 1s

struct Sample {
  uint16_t value;
  uint32_t t_ms;
};

volatile Sample  ringBuf[RING_SIZE];
volatile uint16_t head      = 0;   // next write position
volatile uint16_t last_sent = 0;   // position after last sent sample
volatile bool     overflowed = false;

void setup() {
  Serial.begin(115200);
  Timer1.initialize(SAMPLE_INTERVAL_US);
  Timer1.attachInterrupt(readADC);
}

void loop() {
  if (Serial.available()) {
    int cmd = Serial.read();
    if (cmd == 'R') {
      sendPending();
    }
  }
}

void readADC() {
  uint16_t next = head + 1;
  if (next == RING_SIZE) next = 0;

  // If the ring would overwrite unsent data, drop the oldest (move last_sent forward)
  if (next == last_sent) {
    last_sent = last_sent + 1;
    if (last_sent == RING_SIZE) last_sent = 0;
    overflowed = true;
  }

  ringBuf[head].value = analogRead(A0);
  ringBuf[head].t_ms  = millis();
  head = next;
}

// CRC-16/IBM (Modbus style), poly 0xA001, init 0x0000
uint16_t crc16_update(uint16_t crc, uint8_t data) {
  crc ^= data;
  for (uint8_t i = 0; i < 8; i++) {
    if (crc & 1) {
      crc = (crc >> 1) ^ 0xA001;
    } else {
      crc >>= 1;
    }
  }
  return crc;
}

void sendLE16(uint16_t v, uint16_t &crc) {
  uint8_t b0 = v & 0xFF;
  uint8_t b1 = (v >> 8) & 0xFF;
  Serial.write(b0); crc = crc16_update(crc, b0);
  Serial.write(b1); crc = crc16_update(crc, b1);
}

void sendLE32(uint32_t v, uint16_t &crc) {
  uint8_t b0 = v & 0xFF;
  uint8_t b1 = (v >> 8) & 0xFF;
  uint8_t b2 = (v >> 16) & 0xFF;
  uint8_t b3 = (v >> 24) & 0xFF;
  Serial.write(b0); crc = crc16_update(crc, b0);
  Serial.write(b1); crc = crc16_update(crc, b1);
  Serial.write(b2); crc = crc16_update(crc, b2);
  Serial.write(b3); crc = crc16_update(crc, b3);
}

void sendPending() {
  // Snapshot indices atomically
  noInterrupts();
  uint16_t tail = last_sent;
  uint16_t h    = head;
  bool ovf      = overflowed;
  overflowed    = false;
  interrupts();

  uint16_t count = (h >= tail) ? (h - tail) : (RING_SIZE - tail + h);
  if (count == 0) return;
  if (count > 255) count = 255; // clamp to fit in uint8 count

  uint16_t crc = 0;
  Serial.write((uint8_t)count);
  crc = crc16_update(crc, (uint8_t)count);

  // Send samples in order from tail
  uint16_t idx = tail;
  for (uint16_t i = 0; i < count; i++) {
    if (idx == RING_SIZE) idx = 0;
    sendLE16(ringBuf[idx].value, crc);
    idx++;
  }
  // Send timestamps
  idx = tail;
  for (uint16_t i = 0; i < count; i++) {
    if (idx == RING_SIZE) idx = 0;
    sendLE32(ringBuf[idx].t_ms, crc);
    idx++;
  }

  // crc (little-endian)
  Serial.write(crc & 0xFF);
  Serial.write((crc >> 8) & 0xFF);

  // Advance last_sent to h (or tail + count if clamped)
  noInterrupts();
  last_sent = (tail + count) % RING_SIZE;
  interrupts();
}
