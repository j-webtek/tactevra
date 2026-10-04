// Exercise the actual candidate header with inert firmware interfaces.
#include <stdint.h>
#include <string.h>
#include <math.h>
#include <assert.h>
#include <stdlib.h>
using byte=uint8_t;
struct struct_message {
  byte devCode;float base,shoulder,elbow,wrist,roll,hand;byte cmd;char message[200];
};
struct esp_now_recv_info_t { uint8_t src_addr[6]; };
byte espNowMode=3;bool ctrlByBroadcast=true;uint8_t mac_whitelist_broadcast[6]={};
int moves=0,handlers=0,parses=0;
struct Document { void clear() {} } jsonCmdReceive;
enum class DeserializationError { Ok, InvalidInput };
DeserializationError deserializeJson(Document&,const char* value) {
  ++parses;return strcmp(value,"valid")==0?DeserializationError::Ok:DeserializationError::InvalidInput;
}
struct Printer { void println(const char*) {} } Serial;
void jsonCmdReceiveHandler() { ++handlers; }
void RoArmM3_allJointAbsCtrl(float,float,float,float,float,float,int,int) { ++moves; }
#include "espnow_owner.h"

int main(int argc,char** argv) {
  assert(argc==2);const int scenario=atoi(argv[1]);
  struct_message message={};esp_now_recv_info_t sender={};
  if (scenario==1 || scenario==3) { message.cmd=1;memcpy(message.message,scenario==1?"valid":"bad",scenario==1?6:4); }
  if (scenario==4) message.base=NAN;
  OnDataRecv(&sender,reinterpret_cast<const unsigned char*>(&message),
      scenario==2?sizeof(message)-1:sizeof(message));
  assert(moves==0 && handlers==0 && parses==0); // Callback never executes/parses.
  if (scenario==0) message.base=NAN; // Original buffer mutation cannot change copy.
  processEspNowOwner();
  assert(moves==0 && handlers==0 && parses==0 && !rocellOwnerFault());
  processEspNowOwner();
  assert(moves==0 && handlers==0 && parses==0 && !rocellOwnerFault());
}
