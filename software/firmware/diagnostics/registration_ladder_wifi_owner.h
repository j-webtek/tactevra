// One-write, one-leg registration owner used by the signed Wi-Fi route.
#pragma once
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace rocell_diag {
template<class Services> class RegistrationLadderWifiOwner {
 public:
  using Pose=typename Services::Pose;
  explicit RegistrationLadderWifiOwner(Services& services):services_(services){}
  const char* start_once(){
    if(attempted_)return "ALREADY_ATTEMPTED";
    attempted_=true; // A failed or uncertain attempt is never refundable.
    Pose first{},second{};
    if(!services_.healthy()||!services_.sample(first)||!services_.sample(second)||
       !stable(first,second)||!source(second))return fail("PREWRITE_POSE");
    before_=second;
    if(!services_.write_base(2107,20,1))return fail("WRITE_UNCERTAIN");
    write_count_=1;started_ms_=services_.now_ms();state_=State::Moving;
    return "LEG_ACCEPTED";
  }
  void poll(){
    if(state_!=State::Moving||uint32_t(services_.now_ms()-started_ms_)<8000)return;
    Pose first{},second{};
    if(!services_.healthy()||!services_.sample(first)||!services_.sample(second)||
       !stable(first,second)||!target(second)){fail("POSTWRITE_POSE");return;}
    after_=second;state_=State::Verified;
  }
  bool status(char* output,size_t capacity)const{
    if(!output||capacity<96)return false;
    const char* state=state_==State::Ready?"READY":state_==State::Moving?"MOVING":
                      state_==State::Verified?"VERIFIED":"FAULT";
    const int written=std::snprintf(output,capacity,
      "{\"schema\":\"rocell.registration_ladder_wifi_status.v1\"," 
      "\"state\":\"%s\",\"leg\":1,\"attempted\":%s,\"write_count\":%u,"
      "\"retry_allowed\":false,\"fault\":\"%s\"}",state,
      attempted_?"true":"false",write_count_,fault_);
    return written>0&&size_t(written)<capacity;
  }
 private:
  enum class State:uint8_t{Ready,Moving,Verified,Fault};
  static const uint16_t* source_goals(){
    static const uint16_t value[7]={2047,2075,2039,2600,2233,2040,1897};return value;}
  static const uint16_t* source_positions(){
    static const uint16_t value[7]={2041,2081,2033,2609,2233,2041,1900};return value;}
  static const uint16_t* target_goals(){
    static const uint16_t value[7]={2107,2075,2039,2600,2233,2040,1897};return value;}
  static bool stable(const Pose& a,const Pose& b){
    for(unsigned i=0;i<7;++i)if(!a.torque[i]||!b.torque[i]||a.moving[i]||b.moving[i]||
      a.goal[i]!=b.goal[i]||std::abs(int(a.position[i])-int(b.position[i]))>8)return false;
    return true;
  }
  static bool source(const Pose& pose){
    const auto goals=source_goals(),positions=source_positions();
    for(unsigned i=0;i<7;++i)if(pose.goal[i]!=goals[i]||
      std::abs(int(pose.position[i])-int(positions[i]))>16)return false;
    return true;
  }
  bool target(const Pose& pose)const{
    const auto goals=target_goals();
    for(unsigned i=0;i<7;++i)if(pose.goal[i]!=goals[i]||
      std::abs(int(pose.position[i])-int(i?before_.position[i]:goals[i]))>(i?16:12))return false;
    return true;
  }
  const char* fail(const char* reason){
    state_=State::Fault;std::snprintf(fault_,sizeof(fault_),"%s",reason);return reason;
  }
  Services& services_;Pose before_{},after_{};uint32_t started_ms_=0;
  unsigned write_count_=0;State state_=State::Ready;bool attempted_=false;char fault_[24]{};
};
}
