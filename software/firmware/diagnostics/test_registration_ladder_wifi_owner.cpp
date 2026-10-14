#include <cassert>
#include <cstdint>
#include <cstring>
#include <string>
#include "registration_ladder_wifi_owner.h"

using namespace rocell_diag;
struct Pose {uint16_t position[7]{},goal[7]{};uint8_t torque[7]{},moving[7]{};};
struct Services {
  using Pose=::Pose;
  uint32_t clock=10;unsigned samples=0,writes=0;bool ok=true;
  Pose pose{};
  Services(){
    const uint16_t p[7]={2041,2081,2033,2609,2233,2041,1900};
    const uint16_t g[7]={2047,2075,2039,2600,2233,2040,1897};
    for(unsigned i=0;i<7;++i){pose.position[i]=p[i];pose.goal[i]=g[i];pose.torque[i]=1;}
  }
  bool healthy(){return ok;}
  bool sample(Pose& out){++samples;out=pose;return ok;}
  bool write_base(uint16_t goal,uint16_t speed,uint8_t acceleration){
    assert(goal==2107&&speed==20&&acceleration==1&&writes==0);
    ++writes;pose.goal[0]=goal;return ok;
  }
  uint32_t now_ms(){return clock;}
};
int main(){
  Services services;RegistrationLadderWifiOwner<Services> owner(services);char status[256];
  assert(owner.status(status,sizeof(status))&&std::string(status).find("READY")!=std::string::npos);
  assert(std::string(owner.start_once())=="LEG_ACCEPTED"&&services.writes==1);
  assert(std::string(owner.start_once())=="ALREADY_ATTEMPTED"&&services.writes==1);
  services.clock+=7999;owner.poll();
  assert(owner.status(status,sizeof(status))&&std::string(status).find("MOVING")!=std::string::npos);
  services.pose.position[0]=2105;services.clock+=1;owner.poll();
  assert(owner.status(status,sizeof(status))&&std::string(status).find("VERIFIED")!=std::string::npos);
  Services displaced;displaced.pose.position[0]=2200;
  RegistrationLadderWifiOwner<Services> rejected(displaced);
  assert(std::string(rejected.start_once())=="PREWRITE_POSE"&&displaced.writes==0);
  assert(std::string(rejected.start_once())=="ALREADY_ATTEMPTED"&&displaced.writes==0);
  return 0;
}
