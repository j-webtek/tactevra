// The pinned reference ESP-NOW message has no authenticated sender, freshness
// counter, or reviewed motion admission. Keep this ingress disabled in every
// generated owner candidate until a separate authenticated protocol exists.
bool rocellOwnerFault() { return false; }

void OnDataRecv(const esp_now_recv_info_t* info,
                const unsigned char* data, int length) {
  (void)info;
  (void)data;
  (void)length;
}

void processEspNowOwner() {}
