// Signed, boot-bound Wi-Fi route for one precompiled registration-ladder leg.
// The service owns pose checks and the one physical write; this layer exposes
// no target, joint, speed, acceleration, retry, return, or gripper parameter.
#pragma once
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace rocell_diag {
template<class Services,class Web> class RegistrationLadderWifiRoutes {
 public:
  RegistrationLadderWifiRoutes(Services& services,Web& web,const uint8_t (&boot)[16])
      :services_(services),web_(web){
    static const char digits[]="0123456789abcdef";
    for(unsigned i=0;i<16;++i){boot_[2*i]=digits[boot[i]>>4];boot_[2*i+1]=digits[boot[i]&15];}
    boot_[32]=0;
  }
  void register_routes(){
    if(registered_)return;registered_=true;
    web_.on("/rocell/registration-ladder/leg",HTTP_POST,[this](){leg();});
    web_.on("/rocell/registration-ladder/status",HTTP_GET,[this](){status();});
  }
  void poll(){services_.registration_poll();}
 private:
  bool request_ok(){
    if(web_.authenticated())return true;
    web_.send(403,"text/plain","");return false;
  }
  bool empty(){return web_.args()==0;}
  bool one_plain(){return web_.args()==1&&web_.argName(0)=="plain";}
  static bool hex64(const char* text){
    for(unsigned i=0;i<64;++i)if(!((text[i]>='0'&&text[i]<='9')||
        (text[i]>='a'&&text[i]<='f')))return false;
    return text[64]==':';
  }
  void leg(){
    if(!request_ok())return;
    const auto body=web_.arg("plain");
    char prefix[40];std::snprintf(prefix,sizeof(prefix),"RCLW1:%s:1:",boot_);
    const size_t offset=std::strlen(prefix);
    const char* raw=body.c_str();
    if(!one_plain()||body.length()!=offset+64+16||
       std::strncmp(raw,prefix,offset)||!hex64(raw+offset)||
       std::strcmp(raw+offset+65,"LIVE_NONCONTACT")){
      web_.send(400,"text/plain","");return;
    }
    uint8_t supplied[32]{};
    for(unsigned i=0;i<64;++i){const char c=raw[offset+i];
      const uint8_t value=uint8_t(c<='9'?c-'0':c-'a'+10);
      if(i&1)supplied[i/2]|=value;else supplied[i/2]=uint8_t(value<<4);}
    uint8_t expected[32]{};
    if(!services_.registration_release_digest(expected)||
       std::memcmp(supplied,expected,32)){
      web_.send(409,"text/plain","RELEASE_MISMATCH");return;
    }
    const char* result=services_.registration_start_once();
    const bool accepted=result&&std::strcmp(result,"LEG_ACCEPTED")==0;
    web_.send(accepted?202:409,"text/plain",result?result:"FAULT");
  }
  void status(){
    if(!request_ok())return;
    if(!empty()){web_.send(400,"text/plain","");return;}
    char response[256]{};
    if(!services_.registration_status(response,sizeof(response))){
      web_.send(409,"text/plain","STATUS_UNAVAILABLE");return;
    }
    web_.send(200,"application/json",response);
  }
  Services& services_;Web& web_;char boot_[33]{};bool registered_=false;
};
}
