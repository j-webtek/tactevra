// Adapter joining a hardware backend, fixed-leg owner, and HTTP route facade.
#pragma once
#include "registration_ladder_wifi_owner.h"
#include <cstdint>
#include <cstring>

namespace rocell_diag {
template<class Backend> class RegistrationLadderWifiService {
 public:
  using Pose=typename Backend::Pose;
  RegistrationLadderWifiService(Backend& backend,const uint8_t (&release)[32])
      :backend_(backend),owner_(*this){std::memcpy(release_,release,32);}
  ~RegistrationLadderWifiService(){
    volatile uint8_t* bytes=release_;for(unsigned i=0;i<32;++i)bytes[i]=0;
  }
  RegistrationLadderWifiService(const RegistrationLadderWifiService&)=delete;
  RegistrationLadderWifiService& operator=(const RegistrationLadderWifiService&)=delete;
  bool healthy(){return backend_.healthy();}
  bool sample(Pose& pose){return backend_.sample(pose);}
  bool write_base(uint16_t target,uint16_t speed,uint8_t acceleration){
    return backend_.write_base(target,speed,acceleration);
  }
  uint32_t now_ms(){return backend_.now_ms();}
  bool registration_release_digest(uint8_t (&out)[32]){
    uint8_t any=0;for(auto byte:release_)any|=byte;
    if(!any)return false;std::memcpy(out,release_,32);return true;
  }
  const char* registration_start_once(){return owner_.start_once();}
  bool registration_status(char* output,size_t capacity){return owner_.status(output,capacity);}
  void registration_poll(){owner_.poll();}
 private:
  Backend& backend_;RegistrationLadderWifiOwner<RegistrationLadderWifiService> owner_;
  uint8_t release_[32]{};
};
}
